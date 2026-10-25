"""Versioned reference relocation for known extraction regressions, never a ranker input."""

import re
from collections import Counter
from copy import deepcopy

from app.unseen_report_validation import BOUNDARIES


def validate_registered_questions(corpus, specifications, issuers):
    """Validate identities/questions/boundaries before embeddings or retrieval."""
    docs, cases = corpus["documents"], corpus["cases"]
    if set(docs) != set(issuers) or any(
        docs[k]["symbol"] != symbol for k, symbol in issuers.items()
    ):
        raise ValueError("unregistered issuer")
    prefix = list(range(1, 33))
    if any(
        doc["report_period"] != "2024" or doc["selected_pages"] != prefix for doc in docs.values()
    ):
        raise ValueError("unregistered report or prefix")
    facts = [case for case in cases if case.get("validation_kind") == "fact"]
    boundaries = [case for case in cases if case.get("validation_kind") == "boundary"]
    if (
        len(cases) != len(facts) + len(boundaries)
        or len(facts) != len(issuers) * len(specifications)
        or len({case["id"] for case in cases}) != len(cases)
        or Counter(c.get("boundary_kind") for c in boundaries) != Counter(BOUNDARIES.keys())
    ):
        raise ValueError("unregistered question set")
    wanted = Counter((spec["metric"], spec["period"]) for spec in specifications)
    for key, symbol in issuers.items():
        group = [case for case in facts if case["document_ids"] == [key]]
        if Counter((c["metric"], c["period"]) for c in group) != wanted:
            raise ValueError("unregistered factual request")
        if any(
            c["symbol"] != symbol
            or c["owner"] != "pilot-a"
            or c.get("withdrawn")
            or c["report_period"] != "2024"
            or c["as_of"] <= docs[key]["published_date"]
            for c in group
        ):
            raise ValueError("factual source scope invalid")
    for case in cases:
        if len(case["document_ids"]) != 1 or case["document_ids"][0] not in issuers:
            raise ValueError("unregistered document scope")
        key = case["document_ids"][0]
        if case["context_pages"] != {key: prefix}:
            raise ValueError("unregistered context prefix")
        if case.get("validation_kind") != "boundary":
            continue
        kind, doc = case["boundary_kind"], docs[key]
        conditions = dict(
            future_period=case["period"][:4] > "2024",
            before_publication=case["as_of"] == doc["published_date"],
            wrong_security=case["symbol"] != doc["symbol"],
            wrong_report=case["report_period"] != "2024",
            other_owner=case["owner"] != "pilot-a",
            withdrawn=case.get("withdrawn") is True,
        )
        gold = corpus["gold"][case["id"]]
        if (
            not conditions[kind]
            or gold["status"] != "insufficient"
            or gold["reason_code"] != BOUNDARIES[kind]
        ):
            raise ValueError("boundary condition mismatch")


def relocate_references(old_corpus, new_documents):
    """Keep values/units/PDF identity; changed occurrence counts require manual review.

    Occurrence ordering alone is not semantic certification. Saved old/new excerpts
    must be checked against the original rendered rows before freezing the corpus.
    """
    for key, doc in old_corpus["documents"].items():
        if key not in new_documents or doc["pdf_sha256"] != new_documents[key]["pdf_sha256"]:
            raise ValueError("PDF identity changed")
    gold, changes = deepcopy(old_corpus["gold"]), []
    for case_id, reference in gold.items():
        if reference["status"] != "supported":
            continue
        for anchor in reference["allowed_anchors"]:
            key, page, quote = anchor["document_id"], anchor["page"], anchor["quote"]
            old = old_corpus["documents"][key]["text_pages"][page - 1]["text"]
            new = new_documents[key]["text_pages"][page - 1]["text"]
            pattern = r"(?<![\d.,])" + re.escape(quote) + r"(?![\d.,])"
            previous = list(re.finditer(pattern, old))
            current = list(re.finditer(pattern, new))
            if not previous or len(previous) != len(current):
                raise ValueError("value occurrence count changed; manual review required")
            positions = [m.start() for m in previous]
            if anchor["start"] not in positions:
                raise ValueError("old anchor mismatch")
            match = current[positions.index(anchor["start"])]
            changes.append(
                dict(
                    case_id=case_id,
                    old_anchor=deepcopy(anchor),
                    new_start=match.start(),
                    new_end=match.end(),
                    new_excerpt=new[max(0, match.start() - 90) : match.end() + 70],
                )
            )
            anchor.update(start=match.start(), end=match.end())
        if "anchor" in reference:
            reference["anchor"] = deepcopy(reference["allowed_anchors"][0])
    return gold, changes
