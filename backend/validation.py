from typing import Dict, Any, List, Tuple, Optional
from models import ExtractedFinancials, ExtractedField

# ---------------------------------------------------------------------------
# AUDIT FIX 4 & 5: Strict schema validation layer that runs BEFORE scoring.
# Every field is validated for type, range, and logical consistency.
# The scoring engine only ever receives a fully-validated ExtractedFinancials.
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.6

NUMERIC_FIELDS = {
    "revenue", "ebitda", "pat", "net_worth", "total_debt",
    "current_ratio", "debt_equity_ratio", "interest_coverage_ratio",
    "dscr", "years_in_operation", "promoter_experience_years",
    "collateral_value", "loan_amount_requested", "contingent_liabilities",
}

BOOLEAN_FIELDS = {
    "auditor_qualification", "gst_mismatch", "mca_filing_status",
    "rbi_regulatory_risk", "litigation_pending", "related_party_transactions",
}

# Hard plausibility bounds — values outside these are flagged (not nullified)
PLAUSIBILITY_BOUNDS: Dict[str, Tuple[float, float]] = {
    "current_ratio":             (0.0, 30.0),
    "debt_equity_ratio":         (0.0, 50.0),
    "interest_coverage_ratio":   (-50.0, 200.0),
    "dscr":                      (-10.0, 50.0),
    "years_in_operation":        (0.0, 200.0),
    "promoter_experience_years": (0.0, 80.0),
}

# Fields that must never be negative
MUST_BE_NON_NEGATIVE = {"revenue", "collateral_value", "loan_amount_requested"}


def _coerce_bool(raw: Any) -> Optional[bool]:
    """Return True/False/None — never raise."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        if raw.lower() in ("true", "yes", "1"):
            return True
        if raw.lower() in ("false", "no", "0", "none", "null", ""):
            return False
    return None


def _coerce_float(raw: Any) -> Optional[float]:
    """Return float or None — never raise."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def validate_and_flag(
    raw_data: Dict[str, Any],
) -> Tuple[ExtractedFinancials, List[str]]:
    """
    Full schema validation + flagging before the scoring engine sees data.
    Returns (ExtractedFinancials, warnings_list).

    Gates applied per field:
    1. Must be a dict with value/confidence/evidence keys.
    2. Numeric fields: coerce to float; flag negatives where disallowed.
    3. Boolean fields: coerce to bool; null if ambiguous.
    4. Low confidence (<0.6): flag for manual review.
    5. Plausibility bounds: flag implausible ratios.
    6. Cross-field: PAT > Revenue and EBITDA > Revenue inconsistencies.
    7. Unknown keys from LLM are silently dropped by Pydantic.
    """
    warnings: List[str] = []
    cleaned: Dict[str, Any] = {}

    for fn, fd in raw_data.items():
        # Gate 1: field must be a dict
        if not isinstance(fd, dict):
            warnings.append(
                f"[SCHEMA] Field '{fn}' is not a dict (got {type(fd).__name__}) — nulled."
            )
            cleaned[fn] = ExtractedField(
                value=None, confidence=0.0, evidence="",
                flagged=True, flag_reason="Schema error: not a dict",
            )
            continue

        raw_val = fd.get("value")
        raw_conf = fd.get("confidence", 0.0)
        raw_evid = fd.get("evidence", "")
        flagged = False
        reasons: List[str] = []

        # Gate 2: numeric type coercion + range checks
        if fn in NUMERIC_FIELDS and raw_val is not None:
            coerced = _coerce_float(raw_val)
            if coerced is None:
                warnings.append(
                    f"[TYPE] Field '{fn}' expected numeric, got {raw_val!r} — nulled."
                )
                raw_val = None
                flagged = True
                reasons.append("Non-numeric value nulled")
            else:
                raw_val = coerced
                if fn in MUST_BE_NON_NEGATIVE and raw_val < 0:
                    flagged = True
                    reasons.append(f"Negative value {raw_val:.2f} implausible for '{fn}'")
                    warnings.append(f"[RANGE] '{fn}' is negative ({raw_val:.2f}) — flagged.")
                if fn in PLAUSIBILITY_BOUNDS:
                    lo, hi = PLAUSIBILITY_BOUNDS[fn]
                    if not (lo <= raw_val <= hi):
                        flagged = True
                        reasons.append(
                            f"{raw_val:.2f} outside plausible range [{lo}, {hi}]"
                        )
                        warnings.append(
                            f"[RANGE] '{fn}' = {raw_val:.2f} outside [{lo}, {hi}] — flagged."
                        )

        # Gate 3: boolean type coercion
        if fn in BOOLEAN_FIELDS and raw_val is not None:
            coerced_bool = _coerce_bool(raw_val)
            if coerced_bool is None:
                warnings.append(
                    f"[TYPE] Field '{fn}' has ambiguous boolean value {raw_val!r} — nulled."
                )
                raw_val = None
                flagged = True
                reasons.append(f"Ambiguous boolean nulled")
            else:
                raw_val = coerced_bool

        # Gate 4: low-confidence flag
        try:
            conf_f = max(0.0, min(1.0, float(raw_conf)))
        except (TypeError, ValueError):
            conf_f = 0.0
        if conf_f < CONFIDENCE_THRESHOLD and raw_val is not None:
            flagged = True
            reasons.append(f"Low confidence ({conf_f:.0%}) — verify manually")
            warnings.append(
                f"[CONFIDENCE] '{fn}' has low confidence {conf_f:.0%} — flagged for review."
            )

        cleaned[fn] = ExtractedField(
            value=raw_val,
            confidence=conf_f,
            evidence=str(raw_evid)[:500] if raw_evid else "",
            flagged=flagged,
            flag_reason=" | ".join(reasons) if reasons else None,
        )

    # Gate 5: cross-field logical consistency
    rev_f = cleaned.get("revenue")
    pat_f = cleaned.get("pat")
    if (
        rev_f and pat_f
        and rev_f.value is not None
        and pat_f.value is not None
        and pat_f.value > rev_f.value
    ):
        warnings.append(
            "[CONSISTENCY] PAT exceeds Revenue — likely unit mismatch or misstated figures."
        )
        pat_f.flagged = True
        pat_f.flag_reason = (pat_f.flag_reason or "") + " | PAT > Revenue inconsistency"

    ebit_f = cleaned.get("ebitda")
    if (
        rev_f and ebit_f
        and rev_f.value and rev_f.value > 0
        and ebit_f.value is not None
        and ebit_f.value > rev_f.value
    ):
        warnings.append(
            "[CONSISTENCY] EBITDA exceeds Revenue — likely unit mismatch."
        )
        ebit_f.flagged = True
        ebit_f.flag_reason = (ebit_f.flag_reason or "") + " | EBITDA > Revenue"

    # Construct model — unknown keys silently ignored by Pydantic
    try:
        financials = ExtractedFinancials(**cleaned)
    except Exception as ex:
        warnings.append(f"[MODEL] ExtractedFinancials build warning: {ex}")
        safe = {
            k: v for k, v in cleaned.items()
            if k in ExtractedFinancials.model_fields
        }
        try:
            financials = ExtractedFinancials(**safe)
        except Exception:
            warnings.append("[MODEL] Falling back to empty ExtractedFinancials.")
            financials = ExtractedFinancials()

    return financials, warnings
