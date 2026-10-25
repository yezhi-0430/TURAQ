"""Explanatory unit labels after strict scoring; never mutates scores or answers."""

from decimal import Decimal, InvalidOperation

POLICY_VERSION = "financial-unit-labels-v1"
EPS = {"基本每股收益", "稀释每股收益"}
CANONICAL = {"人民币元": "元", "元／股": "元/股"}


def unit_note(row, case, reference):
    output, scores = row.get("output") or {}, row.get("scores") or {}
    if (
        row.get("task_error")
        or row.get("scoring_error")
        or output.get("status") != "supported"
        or reference.get("status") != "supported"
        or not all(scores.get(key) is True for key in ("identity", "evidence", "abstention"))
        or not isinstance(output.get("unit"), str)
        or not isinstance(reference.get("unit"), str)
    ):
        return None
    try:
        actual, expected = Decimal(output["value"]), Decimal(reference["value"])
        if not actual.is_finite() or not expected.is_finite() or actual != expected:
            return None
    except (InvalidOperation, TypeError, KeyError):
        return None
    model_unit, reference_unit = output["unit"], reference["unit"]
    left = CANONICAL.get(model_unit, model_unit)
    right = CANONICAL.get(reference_unit, reference_unit)
    status, reason = "different", "different_unit"
    if model_unit == reference_unit:
        status, reason = "same", "exact"
    elif left == right:
        status = "equivalent"
        reason = (
            "currency_label" if "人民币元" in {model_unit, reference_unit} else "slash_typography"
        )
    elif case["metric"] in EPS and {left, right} <= {"元", "元/股"}:
        status, reason = "equivalent", "eps_per_share"
    return dict(
        policy_version=POLICY_VERSION,
        status=status,
        reason=reason,
        model_unit=model_unit,
        reference_unit=reference_unit,
        scope="label_equivalence_only_not_rescore",
    )
