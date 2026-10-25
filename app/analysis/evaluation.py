"""Gold-scored facts for exact known PDFs, using the admitted application model."""

from uuid import uuid4

from app import observability
from app.analysis.evidence import VERSION as EVIDENCE_VERSION
from app.analysis.evidence import application_task
from app.analysis.quality import benchmark_for, corpus
from app.analysis.units import POLICY_VERSION, unit_note
from app.context_store import select_combined_evidence
from app.model_limits import (
    LimitsUnavailable,
    ModelDeadlineExceeded,
    RateLimited,
    bind_model,
    public_error,
)
from app.report_evidence_eval import SCORER, evaluate_answers
from app.report_evidence_task import TASK_VERSION


def evaluate_document(sha, client, admission):
    profile = benchmark_for(sha)
    if not profile["available"]:
        raise ValueError("该文件尚无金标，不能运行准确率评测")
    if admission.settings.model_provider != "qwen":
        raise ValueError("当前未启用真实模型，未运行质量评测")
    data = corpus()
    cases = [c for c in data["cases"] if c["document_ids"] == [profile["document_id"]]]
    subset = dict(data, cases=cases)
    model = bind_model(client, admission, purpose="risk_document")
    if hasattr(model, "output_tokens"):
        model.output_tokens = 2048
    def selector(context):
        seconds = min(6, admission.remaining())
        result = select_combined_evidence(
            context, admission.settings, admission.actor_id, seconds=seconds
        )
        admission.remaining()
        return result

    task = application_task(model, selector=selector) if getattr(
        admission.settings, "openviking_enabled", False
    ) else application_task(model)
    runtime_error = None

    def admitted_task(context):
        nonlocal runtime_error
        if runtime_error is not None:
            raise runtime_error
        try:
            return task(context)
        except (RateLimited, LimitsUnavailable, ModelDeadlineExceeded) as exc:
            runtime_error = exc
            raise

    trace_id = uuid4().hex
    token = observability.TRACE.set(trace_id)
    try:
        admission.remaining()
        report = evaluate_answers(
            {}, corpus=subset, mode="application_fact_eval", task=admitted_task
        )
        observability.emit(
            "experiment",
            status="completed",
            requested=report["requested"],
            passed=report["passed"],
            scored=report["scored"],
            integrity_ok=report["integrity_ok"],
        )
        observability.emit("agent_run", status="completed", rounds=len(task.decisions))
    finally:
        observability.TRACE.reset(token)
    totals = {}
    attempts = list(getattr(admission, "model_attempt_usage", []))
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [(a.get("usage") or {}).get(key) for a in attempts]
        totals[key] = (
            sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
        )
    by_id = {c["id"]: c for c in cases}
    result = dict(
        state="completed" if report["integrity_ok"] else "incomplete",
        **{
            k: report[k]
            for k in (
                "requested",
                "scored",
                "passed",
                "integrity_ok",
                "acceptance_ok",
                "task_errors",
                "scoring_errors",
            )
        },
        cases=[
            dict(
                row,
                metric=by_id[row["id"]]["metric"],
                period=by_id[row["id"]]["period"],
                unit_note=unit_note(row, by_id[row["id"]], data["gold"][row["id"]]),
            )
            for row in report["cases"]
        ],
        trace_id=trace_id,
        trace_enabled=observability._exporter is not None,
        usage=totals,
        cost=None,
        scope=profile["scope"],
        model_mode="qwen",
        scorer_version=SCORER,
        task_version=TASK_VERSION,
        evidence_mode=EVIDENCE_VERSION,
        unit_policy_version=POLICY_VERSION,
        context_retrieval=[d.get("retrieval", "local") for d in task.decisions],
    )
    if runtime_error is not None:
        error = public_error(runtime_error)
        result["runtime_failure"] = dict(
            status=error.status_code,
            detail=error.detail,
            headers=error.headers or {},
        )
    return result
