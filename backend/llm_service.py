import os
import re
import json
import time
import logging
from typing import Dict, Any, Optional
from prompts import EXTRACTION_SYSTEM_PROMPT, MANAGEMENT_INSIGHT_SYSTEM_PROMPT, CAM_NARRATIVE_SYSTEM_PROMPT
from models import ManagementInsightFlags

logger = logging.getLogger(__name__)

from google import genai
from google.genai import types

_client = genai.Client(api_key="AIzaSyBcnL-2LwlJFTm6XM1OkAtpL6oJY4995O0")

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

def _call_gemini(system, user_content, max_tokens=4096):
    prompt = system + "\n\n" + user_content
    for attempt in range(3):
        try:
            response = _client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.1,
                )
            )
            return response.text
        except Exception as e:
            logger.warning("Gemini error attempt %d: %s", attempt + 1, e)
            time.sleep(2 ** attempt)
    raise RuntimeError("Gemini API call failed after 3 attempts")
def _extract_json_from_text(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence_stripped = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    fence_stripped = re.sub(r"\s*```$", "", fence_stripped).strip()
    try:
        return json.loads(fence_stripped)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract valid JSON. First 300 chars: {text[:300]!r}")

def _build_null_extraction_skeleton():
    return {k: {"value": None, "confidence": 0.0, "evidence": ""} for k in KNOWN_EXTRACTION_KEYS}

def _sanitise_extraction(data):
    clean = {}
    for key in KNOWN_EXTRACTION_KEYS:
        raw = data.get(key, {})
        if not isinstance(raw, dict):
            clean[key] = {"value": None, "confidence": 0.0, "evidence": ""}
            continue
        clean[key] = {
            "value": raw.get("value"),
            "confidence": raw.get("confidence", 0.0),
            "evidence": raw.get("evidence", ""),
        }
    return clean

def extract_financials_from_text(document_text):
    user_msg = "Extract all financial and compliance data from this document:\n\n" + document_text
    try:
        raw_text = _call_gemini(EXTRACTION_SYSTEM_PROMPT, user_msg, max_tokens=4096)
    except RuntimeError:
        raise
    try:
        parsed = _extract_json_from_text(raw_text)
    except ValueError as e:
        logger.error("JSON parse failed: %s", e)
        return _build_null_extraction_skeleton()
    return _sanitise_extraction(parsed)

def analyze_management_insights(primary_insights):
    if not primary_insights or not primary_insights.strip():
        return ManagementInsightFlags()
    try:
        raw_text = _call_gemini(MANAGEMENT_INSIGHT_SYSTEM_PROMPT, primary_insights[:4000], max_tokens=1024)
        data = _extract_json_from_text(raw_text)
    except Exception as e:
        logger.warning("Management insight failed (%s). Using defaults.", e)
        return ManagementInsightFlags()
    def _safe_bool(key):
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

def generate_cam_narratives(company_name, financials_summary, scoring_summary, rag_context=""):
    rag_section = ""
    if rag_context and rag_context.strip():
        rag_section = "\n\nRELEVANT REGULATORY CONTEXT:\n" + rag_context[:2000]
    user_msg = (
        f"Company: {company_name}\n\nFinancial Data:\n{financials_summary}\n\n"
        f"Scoring Results:\n{scoring_summary}{rag_section}\n\nGenerate the CAM narrative sections."
    )
    fallback = {
        "executive_summary": f"Credit appraisal for {company_name}.",
        "company_profile": "Company profile data available in extracted metrics.",
        "financial_analysis": "Refer to financial metrics table and Five Cs breakdown.",
        "compliance_gst_review": "Refer to rule trigger log for compliance signals.",
        "litigation_legal_risk": "Refer to rule trigger log for litigation flags.",
        "sector_conditions": "Sector and macroeconomic data not available.",
        "justification_narrative": f"Credit decision from Five Cs scoring. {scoring_summary[:300]}",
    }
    try:
        raw_text = _call_gemini(CAM_NARRATIVE_SYSTEM_PROMPT, user_msg, max_tokens=4096)
        data = _extract_json_from_text(raw_text)
    except Exception as e:
        logger.warning("CAM narrative failed (%s). Using fallback.", e)
        return fallback
    result = {}
    for key in REQUIRED_NARRATIVE_KEYS:
        llm_val = data.get(key, "")
        if isinstance(llm_val, str) and llm_val.strip():
            result[key] = llm_val.strip()[:3000]
        else:
            result[key] = fallback[key]
    return result