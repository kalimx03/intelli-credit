import os
import re
import json
import time
import logging
import anthropic
from typing import Dict, Any, Optional
from prompts import EXTRACTION_SYSTEM_PROMPT, MANAGEMENT_INSIGHT_SYSTEM_PROMPT, CAM_NARRATIVE_SYSTEM_PROMPT
from models import ManagementInsightFlags

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AUDIT FIX 1: Robust JSON extraction with multi-strategy recovery.
# AUDIT FIX 6: Full LLM failure fallbacks — never propagate a crash.
# ---------------------------------------------------------------------------

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    """Lazy-initialise client so import never crashes on a missing API key."""
    global _client
    if _client is None:
        api_key = os.environ.get("CLAUDE_API_KEY", "")
        if not api_key:
            raise RuntimeError("CLAUDE_API_KEY environment variable is not set.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


MODEL = "claude-sonnet-4-20250514"

# Whitelist of extraction keys the LLM may return
KNOWN_EXTRACTION_KEYS = {
    "revenue", "ebitda", "pat", "net_worth", "total_debt", "current_ratio",
    "debt_equity_ratio", "interest_coverage_ratio", "dscr", "auditor_qualification",
    "gst_mismatch", "mca_filing_status", "rbi_regulatory_risk", "litigation_pending",
    "contingent_liabilities", "related_party_transactions", "years_in_operation",
    "promoter_experience_years", "industry_sector", "collateral_value",
    "collateral_type", "loan_amount_requested",
}

REQUIRED_NARRATIVE_KEYS = {
    "executive_summary", "company_profile", "financial_analysis",
    "compliance_gst_review", "litigation_legal_risk",
    "sector_conditions", "justification_narrative",
}


def _call_claude(system: str, user_content: str, max_tokens: int = 4096,
                 retries: int = 2) -> str:
    """
    Call Claude with retry on transient errors.
    Raises RuntimeError only if all retries exhausted.
    """
    client = _get_client()
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            return message.content[0].text
        except anthropic.RateLimitError as e:
            wait = 2 ** attempt
            logger.warning("Rate limit hit, retrying in %ds (attempt %d)", wait, attempt + 1)
            time.sleep(wait)
            last_exc = e
        except anthropic.APIStatusError as e:
            logger.warning("API error %s on attempt %d: %s", e.status_code, attempt + 1, e.message)
            last_exc = e
            if attempt < retries:
                time.sleep(1)
        except Exception as e:
            logger.error("Unexpected Claude error: %s", e)
            last_exc = e
            break
    raise RuntimeError(f"Claude API call failed after {retries + 1} attempts: {last_exc}")


def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    AUDIT FIX 1: Multi-strategy JSON recovery.

    Strategy 1 — Direct parse (LLM behaved correctly).
    Strategy 2 — Strip markdown fences (```json ... ``` or ``` ... ```).
    Strategy 3 — Find first {...} block via regex.
    Strategy 4 — Balanced-brace scan from last opening brace.
    Raises ValueError only if all strategies fail.
    """
    text = text.strip()

    # Strategy 1: direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    fence_stripped = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    fence_stripped = re.sub(r"\s*```$", "", fence_stripped).strip()
    try:
        return json.loads(fence_stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 3: regex — first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Strategy 4: balanced-brace scan from last opening brace
    start = text.rfind("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start: i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(
        f"Could not extract valid JSON from LLM response. "
        f"First 300 chars: {text[:300]!r}"
    )


def _build_null_extraction_skeleton() -> Dict[str, Any]:
    """
    AUDIT FIX 6: If extraction fails completely, return a fully-null skeleton
    so validation and scoring can still proceed with warnings instead of crashing.
    """
    return {
        k: {"value": None, "confidence": 0.0, "evidence": ""}
        for k in KNOWN_EXTRACTION_KEYS
    }


def _sanitise_extraction(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AUDIT FIX 4 (pre-validation schema guard):
    - Strip unknown keys that LLM may hallucinate.
    - Ensure every entry has the required sub-keys.
    - Coerce sub-key types so Pydantic never chokes.
    """
    clean: Dict[str, Any] = {}
    for key in KNOWN_EXTRACTION_KEYS:
        raw = data.get(key, {})
        if not isinstance(raw, dict):
            clean[key] = {"value": None, "confidence": 0.0, "evidence": ""}
            continue
        clean[key] = {
            "value":      raw.get("value"),
            "confidence": raw.get("confidence", 0.0),
            "evidence":   raw.get("evidence", ""),
        }
    return clean


def extract_financials_from_text(document_text: str) -> Dict[str, Any]:
    """
    AUDIT FIX 6: Always returns a dict of field objects, even on total failure.
    Raises RuntimeError only when the Claude API itself is unreachable.
    """
    user_msg = (
        "Extract all financial and compliance data from this document:\n\n"
        + document_text
    )
    try:
        raw_text = _call_claude(EXTRACTION_SYSTEM_PROMPT, user_msg, max_tokens=4096)
    except RuntimeError:
        raise  # re-raise so main.py returns HTTP 502

    try:
        parsed = _extract_json_from_text(raw_text)
    except ValueError as e:
        logger.error("JSON parse failed after all strategies: %s", e)
        return _build_null_extraction_skeleton()

    return _sanitise_extraction(parsed)


def analyze_management_insights(primary_insights: str) -> ManagementInsightFlags:
    """
    AUDIT FIX 6: On any failure, return safe default flags (all False).
    This function must never raise — management insights are non-critical.
    """
    if not primary_insights or not primary_insights.strip():
        return ManagementInsightFlags()

    try:
        raw_text = _call_claude(
            MANAGEMENT_INSIGHT_SYSTEM_PROMPT,
            primary_insights[:4000],
            max_tokens=1024,
        )
        data = _extract_json_from_text(raw_text)
    except Exception as e:
        logger.warning("Management insight analysis failed (%s). Using defaults.", e)
        return ManagementInsightFlags()

    def _safe_bool(key: str) -> bool:
        v = data.get(key, False)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")

    raw_signals = data.get("raw_signals", [])
    if not isinstance(raw_signals, list):
        raw_signals = []
    raw_signals = [str(s)[:200] for s in raw_signals[:10] if s]

    return ManagementInsightFlags(
        promoter_concern=_safe_bool("promoter_concern"),
        succession_risk=_safe_bool("succession_risk"),
        sector_headwind=_safe_bool("sector_headwind"),
        regulatory_concern=_safe_bool("regulatory_concern"),
        concentration_risk=_safe_bool("concentration_risk"),
        expansion_risk=_safe_bool("expansion_risk"),
        positive_management=_safe_bool("positive_management"),
        raw_signals=raw_signals,
    )


def generate_cam_narratives(
    company_name: str,
    financials_summary: str,
    scoring_summary: str,
    rag_context: str = "",
) -> Dict[str, str]:
    """
    RAG-ENHANCED: Regulatory context from ChromaDB is injected into the prompt.
    This gives Claude access to relevant RBI/GST/MCA norms when writing narratives.
    AUDIT FIX 6: On failure, returns a full set of placeholder narratives.
    """
    rag_section = ""
    if rag_context and rag_context.strip():
        rag_section = f"\n\nRELEVANT REGULATORY CONTEXT (from knowledge base):\n{rag_context[:2000]}"

    user_msg = (
        f"Company: {company_name}\n\n"
        f"Financial Data:\n{financials_summary}\n\n"
        f"Scoring Results:\n{scoring_summary}"
        f"{rag_section}\n\n"
        "Generate the CAM narrative sections. Where relevant, cite the regulatory "
        "context provided (RBI norms, GST guidelines, etc.) in your narratives."
    )
    fallback = {
        "executive_summary": (
            f"Credit appraisal for {company_name}. "
            "Narrative generation was unavailable; refer to quantitative sections."
        ),
        "company_profile": "Company profile data available in extracted metrics.",
        "financial_analysis": "Refer to financial metrics table and Five Cs breakdown.",
        "compliance_gst_review": "Refer to rule trigger log for compliance signals.",
        "litigation_legal_risk": "Refer to rule trigger log for litigation flags.",
        "sector_conditions": "Sector and macroeconomic data not available.",
        "justification_narrative": (
            f"Credit decision derived from deterministic Five Cs scoring engine. "
            f"Scoring summary: {scoring_summary[:300]}"
        ),
    }

    try:
        raw_text = _call_claude(CAM_NARRATIVE_SYSTEM_PROMPT, user_msg, max_tokens=4096)
        data = _extract_json_from_text(raw_text)
    except Exception as e:
        logger.warning("CAM narrative generation failed (%s). Using fallback text.", e)
        return fallback

    result: Dict[str, str] = {}
    for key in REQUIRED_NARRATIVE_KEYS:
        llm_val = data.get(key, "")
        if isinstance(llm_val, str) and llm_val.strip():
            result[key] = llm_val.strip()[:3000]
        else:
            result[key] = fallback[key]
            logger.warning("CAM narrative key '%s' missing or empty; using fallback.", key)

    return result
