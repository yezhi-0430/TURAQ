"""Pre-registration and reference checks for a frozen first-transfer experiment."""

import hashlib
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.report_evidence_eval import load_corpus, local_path, read_json, score_answer

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = {
    "future_period": "period_not_present",
    "before_publication": "not_yet_public",
    "wrong_security": "wrong_security",
    "wrong_report": "sources_unavailable",
    "other_owner": "sources_unavailable",
    "withdrawn": "sources_unavailable",
}


def load_transfer_corpus():
    root = ROOT / "evaluations/turaq/unseen-reports"
    corpus = load_corpus(root)
    protocol = read_json(root / "protocol.json")
    counts = verify_protocol(corpus, protocol, read_json(root / "fixture_answers.json"))
    return corpus, protocol, counts


def verify_protocol(corpus, protocol, fixtures, *, repository_root=ROOT):
    for group in ("algorithm_sha256", "prior_sha256"):
        for name, expected in protocol[group].items():
            if (
                hashlib.sha256(local_path(repository_root, name).read_bytes()).hexdigest()
                != expected
            ):
                raise ValueError("frozen algorithm or prior artifact changed")
    docs, cases, gold = corpus["documents"], corpus["cases"], corpus["gold"]
    issuers = {i["id"]: i["symbol"] for i in protocol["issuers"]}
    prefix = list(range(1, 33))
    if protocol["selected_pages"] != prefix or set(docs) != set(issuers) or len(issuers) != 2:
        raise ValueError("unregistered document selection")
    for key, doc in docs.items():
        if (
            doc["symbol"] != issuers[key]
            or doc["report_period"] != protocol["report_period"]
            or doc["selected_pages"] != prefix
        ):
            raise ValueError("unregistered document scope")
    facts = [c for c in cases if c.get("validation_kind") == "fact"]
    boundaries = [c for c in cases if c.get("validation_kind") == "boundary"]
    if (
        len(cases) != protocol["total_requests"]
        or len(facts) != protocol["factual_requests"]
        or len(boundaries) != protocol["boundary_requests"]
        or len(facts) + len(boundaries) != len(cases)
        or Counter(c.get("boundary_kind") for c in boundaries) != Counter(BOUNDARIES.keys())
        or set(fixtures) != {c["id"] for c in cases}
    ):
        raise ValueError("unregistered case set")
    expected = Counter((spec["metric"], spec["period"]) for spec in protocol["factual_specs"])
    for key, symbol in issuers.items():
        selected = [c for c in facts if c["document_ids"] == [key]]
        if Counter((c["metric"], c["period"]) for c in selected) != expected:
            raise ValueError("factual questions changed")
        if any(
            c["symbol"] != symbol
            or c["report_period"] != protocol["report_period"]
            or c["owner"] != "pilot-a"
            or c.get("withdrawn")
            or c["as_of"] <= docs[key]["published_date"]
            for c in selected
        ):
            raise ValueError("invalid factual source scope")
    supported = 0
    for case in cases:
        for key in case["document_ids"]:
            if key not in docs or case["context_pages"].get(key) != prefix:
                raise ValueError("context outside registered prefix")
        reference = gold[case["id"]]
        if case.get("validation_kind") == "boundary":
            kind = case["boundary_kind"]
            doc = docs[case["document_ids"][0]]
            checks = dict(
                future_period=case["period"][:4] > doc["report_period"],
                before_publication=case["as_of"] == doc["published_date"],
                wrong_security=all(
                    case["symbol"] != docs[k]["symbol"] for k in case["document_ids"]
                ),
                wrong_report=case["report_period"] != doc["report_period"],
                other_owner=case["owner"] != "pilot-a",
                withdrawn=case.get("withdrawn") is True,
            )
            if (
                not checks[kind]
                or reference["status"] != "insufficient"
                or reference["reason_code"] != BOUNDARIES[kind]
            ):
                raise ValueError("boundary condition or reference mismatch")
        elif reference["status"] == "supported":
            supported += 1
            if not reference.get("allowed_anchors"):
                raise ValueError("supported reference has no source")
            for anchor in reference["allowed_anchors"]:
                key, page = anchor["document_id"], anchor["page"]
                if key not in case["document_ids"] or page not in prefix:
                    raise ValueError("anchor outside source scope")
                text = docs[key]["text_pages"][page - 1]["text"]
                start, end = anchor["start"], anchor["end"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(text)
                    or text[start:end] != anchor["quote"]
                ):
                    raise ValueError("anchor is not a literal source span")
                try:
                    quoted = Decimal(re.sub(r"[\s,%％]", "", anchor["quote"]))
                    expected_value = Decimal(reference["value"])
                    if not quoted.is_finite() or quoted != expected_value:
                        raise ValueError("reference value and quote mismatch")
                except InvalidOperation as exc:
                    raise ValueError("reference numeric format invalid") from exc
        elif reference.get("reason_code") not in {"evidence_not_found", "period_not_present"}:
            raise ValueError("invalid unavailable-fact reason")
        if not all(score_answer(fixtures[case["id"]], case, corpus).values()):
            raise ValueError("reference fixture does not pass the unchanged scorer")
    return dict(
        factual_requests=len(facts),
        supported_facts=supported,
        boundary_requests=len(boundaries),
        indexed_pages=len(prefix) * len(docs),
    )


def located_unit_evidence(gold, units):
    """A value repeated on one page only counts at a registered source position."""
    if gold["status"] != "supported":
        return dict(at1=None, at3=None)

    def hit(selected):
        for unit in selected:
            for anchor in gold["allowed_anchors"]:
                if unit["document_id"] != anchor["document_id"] or unit["page"] != anchor["page"]:
                    continue
                for part in unit["parts"]:
                    start, end = part.get("char_start"), part.get("char_end")
                    if (
                        type(start) is not int
                        or type(end) is not int
                        or start < 0
                        or end - start != len(part["text"])
                        or not start <= anchor["start"] < anchor["end"] <= end
                    ):
                        continue
                    if (
                        part["text"][anchor["start"] - start : anchor["end"] - start]
                        == anchor["quote"]
                    ):
                        return True
        return False

    return dict(at1=hit(units[:1]), at3=hit(units[:3]))


def transfer_gate(summary, *, supported_count):
    evidence = summary.get("evidence", {})
    hit = evidence.get("at3")
    return (
        type(supported_count) is int
        and supported_count > 0
        and type(hit) is int
        and 0 <= hit <= supported_count
        and evidence.get("denominator") == supported_count
        and summary.get("requested") == summary.get("recorded") == 22
        and summary.get("errors") == 0
        and summary.get("scope_boundaries_empty") is True
        and hit / supported_count >= 0.75
    )


def scope_boundaries_ok(rows, cases):
    """Every registered blocked case must be present exactly once and remain empty."""
    expected = {
        case["id"]
        for case in cases
        if case.get("validation_kind") == "boundary"
        and case.get("boundary_kind") in BOUNDARIES
        and case["boundary_kind"] != "future_period"
    }
    if len(expected) != 5:
        return False
    for identity in expected:
        matching = [row for row in rows if row["id"] == identity]
        if (
            len(matching) != 1
            or matching[0].get("eligible_resources") != 0
            or matching[0].get("units") != []
            or matching[0].get("error")
        ):
            return False
    return True
