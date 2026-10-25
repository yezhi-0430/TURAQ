"""Explicit cosine semantics, independent of the collection's distance metric."""

import math
from numbers import Real


def cosine_similarity(query, document):
    """Return None for missing, malformed, zero, or non-finite vectors."""
    if query is None or document is None:
        return None
    try:
        if not len(query) or len(query) != len(document):
            return None
        if any(
            isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v)
            for vector in (query, document)
            for v in vector
        ):
            return None
        qnorm, dnorm = math.hypot(*query), math.hypot(*document)
        if not qnorm or not dnorm or not math.isfinite(qnorm) or not math.isfinite(dnorm):
            return None
        score = math.fsum((q / qnorm) * (d / dnorm) for q, d in zip(query, document, strict=True))
        return max(-1.0, min(1.0, score)) if math.isfinite(score) else None
    except (TypeError, ValueError, OverflowError):
        return None


def relevant_results(rows, minimum=0.5):
    """No distance conversion or optimistic fallback when a score is missing."""
    return [
        row
        for row in rows
        if type(row.get("similarity")) in (int, float)
        and math.isfinite(row["similarity"])
        and -1 <= row["similarity"] <= 1
        and row["similarity"] >= minimum
    ]
