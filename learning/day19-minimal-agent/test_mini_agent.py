"""Offline behavioral tests: no application, database, network, or reference imports."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import mini_agent as agent


def request(call_id="c1", name="add", arguments=None):
    return {
        "id": call_id,
        "name": name,
        "arguments": {"a": 3, "b": 5} if arguments is None else arguments,
    }


def calls(*items):
    return {"content": None, "tool_calls": list(items)}


def answer(text="done"):
    return {"content": text, "tool_calls": []}


def add(a, b):
    return a + b


def fail():
    raise ValueError("fixture failure")


class AgentTests(unittest.TestCase):
    def test_tool_success_exactly_once(self):
        seen = []

        def echo(text):
            seen.append(text)
            return text

        self.assertEqual(
            agent.execute_tool({"echo": echo}, "echo", {"text": "sample"}),
            {"status": "success", "result": "sample"},
        )
        self.assertEqual(seen, ["sample"])

    def test_unknown_tool_does_not_execute(self):
        seen = []
        result = agent.execute_tool({"add": lambda: seen.append(1)}, "missing", {})
        self.assertEqual(result, {"status": "error", "error": "工具不存在"})
        self.assertEqual(seen, [])

    def test_tool_exception_is_error(self):
        self.assertEqual(
            agent.execute_tool({"fail": fail}, "fail", {}),
            {"status": "error", "error": "fixture failure"},
        )

    def test_invalid_arguments_are_errors(self):
        for arguments in ([], {"a": 3}):
            with self.subTest(arguments=arguments):
                result = agent.execute_tool({"add": add}, "add", arguments)
                self.assertIsInstance(result, dict)
                self.assertEqual(result["status"], "error")

    def test_non_json_result_is_error(self):
        result = agent.execute_tool({"bad": lambda: {1, 2}}, "bad", {})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")

    def test_first_answer_stops(self):
        model = agent.ScriptedModel([answer("hello")])
        result = agent.run_agent(model, {}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(
            (result["status"], result["rounds"], result["answer"]), ("completed", 1, "hello")
        )
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(result["executions"], [])

    def test_tool_result_sent_next_round_with_matching_id(self):
        model = agent.ScriptedModel([calls(request()), answer("8")])
        original = [{"role": "user", "content": "add 3 and 5"}]
        result = agent.run_agent(model, {"add": add}, original)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(len(original), 1)
        outgoing = model.requests[1]
        self.assertEqual(outgoing[-2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(outgoing[-1]["role"], "tool")
        self.assertEqual(outgoing[-1]["tool_call_id"], "c1")
        self.assertEqual(json.loads(outgoing[-1]["content"])["result"], 8)

    def test_success_and_failure_both_recorded(self):
        model = agent.ScriptedModel(
            [
                calls(request(), request("c2", "fail", {})),
                answer("one failure"),
            ]
        )
        result = agent.run_agent(model, {"add": add, "fail": fail}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual([r["status"] for r in result["executions"]], ["success", "error"])
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(len([m for m in model.requests[1] if m["role"] == "tool"]), 2)

    def test_round_limit_has_no_extra_request(self):
        model = agent.ScriptedModel([calls(request(str(n))) for n in range(4)])
        result = agent.run_agent(model, {"add": add}, [], max_rounds=3)
        self.assertIsInstance(result, dict)
        self.assertEqual(
            (result["status"], result["rounds"], result["answer"]), ("max_rounds_exceeded", 3, None)
        )
        self.assertEqual(len(model.requests), 3)
        self.assertEqual(len(result["executions"]), 3)

    def test_empty_reply_is_not_completion(self):
        result = agent.run_agent(agent.ScriptedModel([answer("")]), {}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "invalid_response")

    def test_model_failure_keeps_trace(self):
        model = agent.ScriptedModel([calls(request())])
        result = agent.run_agent(model, {"add": add}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(len(result["executions"]), 1)

    def test_invalid_round_limit(self):
        for limit in (0, -1, True):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    agent.run_agent(agent.ScriptedModel([]), {}, [], max_rounds=limit)

    def test_saved_history_survives_new_process_and_reaches_model(self):
        with TemporaryDirectory(prefix="day19-session-") as directory:
            original = {
                "messages": [{"role": "user", "content": "Meeting is Friday."}],
                "executions": [{"tool_call_id": "old", "status": "success"}],
            }
            agent.save_session(directory, "session-a", original)
            self.assertTrue((Path(directory) / "session-a.json").is_file())
            code = (
                "import json,sys; from mini_agent import load_session; "
                "print(json.dumps(load_session(sys.argv[1],sys.argv[2])))"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, directory, "session-a"],
                cwd=Path(__file__).parent,
                capture_output=True,
                text=True,
                check=True,
            )
            restored = json.loads(proc.stdout)
            self.assertEqual(restored, original)
            restored["messages"].append({"role": "user", "content": "Which day?"})
            model = agent.ScriptedModel([answer("Friday")])
            result = agent.run_agent(
                model,
                {},
                restored["messages"],
                prior_executions=restored["executions"],
            )
            self.assertEqual(model.requests[0][0]["content"], "Meeting is Friday.")
            self.assertEqual(result["executions"], original["executions"])
            self.assertEqual(
                agent.load_session(directory, "session-b"), {"messages": [], "executions": []}
            )

    def test_corrupt_session_is_not_silently_reset(self):
        with TemporaryDirectory(prefix="day19-corrupt-") as directory:
            (Path(directory) / "broken.json").write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                agent.load_session(directory, "broken")

    def test_session_id_cannot_escape_directory(self):
        with TemporaryDirectory(prefix="day19-boundary-") as directory:
            with self.assertRaises(ValueError):
                agent.save_session(directory, "../outside", {"messages": [], "executions": []})


if __name__ == "__main__":
    unittest.main()
