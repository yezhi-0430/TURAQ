"""Evaluate quote-only proposals with the unchanged frozen fact/citation scorer."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from app.report_evidence_eval import (
    CORPUS,
    EvaluationBudget,
    build_context,
    evaluate_answers,
    load_corpus,
    read_json,
)
from app.report_fact_task import TASK_VERSION, QuoteFactAnswer, fact_task, system_prompt
from app.research_eval import digest


def _finish(report, task, context_ids):
    report.update(
        task_version=TASK_VERSION,
        raw_responses=task.raw_responses,
        decisions=[dict(id=context_ids[d["context_sha256"]], **d) for d in task.decisions],
        automatic_promotion=False,
    )
    report["fingerprints"].update(
        prompt=digest(system_prompt()),
        proposal_schema=digest(QuoteFactAnswer.model_json_schema()),
        task_code=hashlib.sha256(
            Path(__file__).with_name("report_fact_task.py").read_bytes()
        ).hexdigest(),
        runner_code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    return report


def evaluate_proposals(proposals, *, corpus=None):
    """Offline input is a mechanism check, never a new model quality measurement."""
    if not isinstance(proposals, dict):
        raise ValueError("proposals must map case IDs to quote-only answers")
    corpus = corpus or load_corpus()
    context_ids = {digest(build_context(case, corpus)): case["id"] for case in corpus["cases"]}

    class Offline:
        def chat(self, messages):
            key = context_ids[digest(json.loads(messages[1]["content"]))]
            return json.dumps(proposals[key], ensure_ascii=False)

    task = fact_task(Offline())

    def require_input(context):
        if context_ids[digest(context)] not in proposals:
            raise KeyError("MissingProposal")
        return task(context)

    report = evaluate_answers(
        {}, corpus=corpus, mode="quote_only_offline_proposals", task=require_input
    )
    unexpected = sorted(set(proposals) - set(report["expected_ids"]))
    if unexpected:
        report.update(unexpected_ids=unexpected, integrity_ok=False, acceptance_ok=False)
    report.update(
        provider_calls=0,
        real_model_quality="not_run",
        execution_claim="offline_proposals_only",
    )
    return _finish(report, task, context_ids)


def make_client(key, http, model):
    from app.llm_client import QwenModelClient

    return QwenModelClient(key, http, model_name=model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["score", "live"], default="score")
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 600 or not 1 <= args.attempts <= 40:
        parser.error("budget must be 1..600 seconds and 1..40 attempts")
    if args.mode == "live" and (
        not args.allow_paid_model or not args.model or not os.getenv("DASHSCOPE_API_KEY")
    ):
        parser.error("live requires --allow-paid-model, --model and DASHSCOPE_API_KEY")
    if args.mode == "score" and args.answers is None:
        parser.error("score requires --answers with quote-only proposals")
    if args.mode == "live" and args.answers is not None:
        parser.error("live cannot consume offline --answers")
    output = args.output.resolve()
    if (
        output.exists()
        or (
            output.is_relative_to(CORPUS.resolve())
            and not output.is_relative_to((CORPUS / "results").resolve())
        )
        or (args.answers and output == args.answers.resolve())
    ):
        parser.error("output must be new and must not overwrite inputs or frozen corpus")
    corpus = load_corpus()
    if args.mode == "score":
        report = evaluate_proposals(read_json(args.answers), corpus=corpus)
        report["input_sha256"] = hashlib.sha256(args.answers.read_bytes()).hexdigest()
    else:
        import httpx

        budget = EvaluationBudget(seconds=args.seconds, attempts=args.attempts)
        with httpx.Client(trust_env=False) as http:
            client = make_client(os.environ["DASHSCOPE_API_KEY"], http, args.model)
            client.admission, client.output_tokens = budget, 2048
            task = fact_task(client)
            report = evaluate_answers({}, corpus=corpus, mode="quote_only_live", task=task)
            context_ids = {digest(build_context(c, corpus)): c["id"] for c in corpus["cases"]}
            _finish(report, task, context_ids)
            report.update(
                model_requested=args.model,
                model_resolved=None,
                attempts=budget.attempts,
                attempt_usage=list(client.attempt_usage),
                provider_calls=budget.attempts,
                budget=dict(
                    seconds=args.seconds, max_attempts=args.attempts, max_output_tokens=2048
                ),
                execution_claim="qwen_client_attempts_recorded",
                real_model_quality="limited_curated_fact_eval_not_general_research",
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("mode", "requested", "passed", "provider_calls")}))
    return 0 if report["acceptance_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
