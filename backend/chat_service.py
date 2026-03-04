"""
CHAT SERVICE — RAG-Powered Credit Q&A
=======================================

HOW IT WORKS (plain English):
  1. Analyst types a question: "Why was this company rejected?"
  2. We embed that question → get a 384-number vector
  3. ChromaDB finds the 4 most similar regulation chunks from our knowledge base
  4. We build a prompt that contains:
       - The full analysis data (scores, financials, triggered rules)
       - The retrieved regulation chunks (RBI norms, GST rules, etc.)
       - The question itself
  5. Claude reads all of this and answers, citing actual regulations
  6. We return the answer + which sources were used (for transparency)

The analyst gets a grounded answer — not Claude guessing.
"""

import logging
from typing import List, Dict, Any, Optional

from rag_engine import retrieve_context, format_context_for_prompt, get_historical_context

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are Intelli-Credit's AI credit analyst assistant for Indian banking.

You help bank officers understand credit appraisal reports and Indian banking regulations.

You have two sources of information:
1. The ANALYSIS DATA — actual extracted financials, Five Cs scores, and triggered risk rules
2. REGULATORY CONTEXT — relevant RBI/GST/MCA guidelines retrieved from the knowledge base

Your rules:
- Always cite specific numbers from the analysis (e.g. "DSCR of 1.15x", "D/E ratio 3.8x")
- When citing regulations, say which guideline it comes from (e.g. "As per RBI IRACP norms...")
- If something is not in the analysis data, say "the analysis does not contain this information"
- Never invent financial figures
- Keep answers focused and under 200 words unless the question requires more
- Use plain language — the audience is credit officers, not data scientists
"""


def _build_analysis_summary(data: Dict[str, Any]) -> str:
    """Turn the full analysis dict into a compact readable text for the LLM."""
    fin     = data.get("extracted_financials", {})
    scoring = data.get("scoring_result", {})
    warns   = data.get("validation_warnings", [])

    def fv(field: str):
        """Get value safely from extracted financials."""
        f = fin.get(field, {})
        return f.get("value") if isinstance(f, dict) else None

    five_cs = scoring.get("five_cs", {})

    lines = [
        f"COMPANY: {data.get('company_name', 'Unknown')}",
        "",
        f"DECISION: {scoring.get('decision', 'N/A')}",
        f"SCORE:    {scoring.get('final_score', 0):.1f} / 100",
        f"RISK:     {scoring.get('risk_band', 'N/A')}",
        f"LOAN LIMIT SUGGESTED: {scoring.get('suggested_loan_limit', 0):,.0f} INR",
        f"RATE SUGGESTED:       {scoring.get('suggested_interest_rate', 0)}% p.a.",
        "",
        "FIVE Cs SCORES (out of 100):",
        f"  Character  (25% weight): {five_cs.get('character', 'N/A')}",
        f"  Capacity   (30% weight): {five_cs.get('capacity',  'N/A')}",
        f"  Capital    (20% weight): {five_cs.get('capital',   'N/A')}",
        f"  Collateral (15% weight): {five_cs.get('collateral','N/A')}",
        f"  Conditions (10% weight): {five_cs.get('conditions','N/A')}",
        "",
        "KEY FINANCIALS:",
    ]

    numeric_fields = [
        ("Revenue",              "revenue"),
        ("EBITDA",               "ebitda"),
        ("PAT (Net Profit)",     "pat"),
        ("Net Worth",            "net_worth"),
        ("Total Debt",           "total_debt"),
        ("Current Ratio",        "current_ratio"),
        ("Debt/Equity Ratio",    "debt_equity_ratio"),
        ("Interest Coverage",    "interest_coverage_ratio"),
        ("DSCR",                 "dscr"),
        ("Years in Operation",   "years_in_operation"),
        ("Industry Sector",      "industry_sector"),
        ("Collateral Value",     "collateral_value"),
        ("Loan Requested",       "loan_amount_requested"),
    ]
    for label, field in numeric_fields:
        v = fv(field)
        if v is not None:
            lines.append(f"  {label}: {v}")

    compliance_fields = [
        ("Auditor Qualification (risk if Yes)", "auditor_qualification"),
        ("GST 2A/3B Mismatch",                  "gst_mismatch"),
        ("MCA Filing Default",                   "mca_filing_status"),
        ("RBI Regulatory Risk",                  "rbi_regulatory_risk"),
        ("Litigation Pending",                   "litigation_pending"),
        ("Related Party Transactions",           "related_party_transactions"),
    ]
    lines.append("")
    lines.append("COMPLIANCE FLAGS (Yes = risk flag):")
    for label, field in compliance_fields:
        v = fv(field)
        if v is not None:
            lines.append(f"  {label}: {'YES ⚠️' if v else 'No'}")

    rule_log = scoring.get("rule_log", [])
    triggered = [r for r in rule_log if r.get("triggered")]
    if triggered:
        lines.append("")
        lines.append(f"RISK RULES TRIGGERED ({len(triggered)}):")
        for r in triggered:
            lines.append(
                f"  [{r.get('category','').upper()}] {r.get('rule_name','')} "
                f"→ score impact: {r.get('impact', 0):+.0f}"
            )

    mgmt = scoring.get("management_flags", {})
    mgmt_on = [k for k, v in mgmt.items() if v is True and k != "raw_signals"]
    if mgmt_on:
        lines.append("")
        lines.append(f"MANAGEMENT FLAGS: {', '.join(mgmt_on)}")

    if warns:
        lines.append("")
        lines.append(f"DATA QUALITY WARNINGS ({len(warns)}):")
        for w in warns[:4]:
            lines.append(f"  {w}")

    return "\n".join(lines)


def answer_question(
    question: str,
    analysis_data: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Core RAG + LLM pipeline:
      query → embed → retrieve → build prompt → Claude → return answer + sources
    """
    import anthropic
    import os

    # ── Step 1: RAG retrieval ─────────────────────────────────────────────
    all_chunks = []
    try:
        # Retrieve regulation chunks relevant to the question
        reg_chunks = retrieve_context(question, n_results=3)

        # Also retrieve historical peer decisions
        score = analysis_data.get("scoring_result", {}).get("final_score", 50)
        sector = None
        fin = analysis_data.get("extracted_financials", {})
        sf = fin.get("industry_sector", {})
        if isinstance(sf, dict):
            sector = sf.get("value")
        hist_chunks = get_historical_context(score, sector)

        # Combine, deduplicate by title
        seen = set()
        for chunk in reg_chunks + hist_chunks:
            if chunk["title"] not in seen:
                all_chunks.append(chunk)
                seen.add(chunk["title"])

        rag_context = format_context_for_prompt(all_chunks[:4])
    except Exception as e:
        logger.warning("RAG retrieval failed for chat (%s) — answering without context.", e)
        rag_context = "Regulatory context temporarily unavailable."

    # ── Step 2: Build analysis summary ───────────────────────────────────
    analysis_summary = _build_analysis_summary(analysis_data)

    # ── Step 3: Build messages ────────────────────────────────────────────
    messages = []

    # Include prior conversation (last 6 turns for token budget)
    if conversation_history:
        for turn in conversation_history[-6:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": str(turn["content"])})

    # Current question with full context
    user_content = (
        f"ANALYSIS DATA:\n{analysis_summary}"
        f"\n\nREGULATORY CONTEXT (retrieved from knowledge base):\n{rag_context}"
        f"\n\nQUESTION: {question}"
    )
    messages.append({"role": "user", "content": user_content})

    # ── Step 4: Call Claude ───────────────────────────────────────────────
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY", ""))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error("Chat LLM call failed: %s", e)
        answer = (
            f"I encountered an error: {e}. "
            "Please check your CLAUDE_API_KEY and try again."
        )

    # ── Step 5: Return with sources ───────────────────────────────────────
    sources = [
        {"title": c["title"], "category": c["category"], "relevance": c["score"]}
        for c in all_chunks[:4]
    ]

    return {
        "answer":          answer,
        "sources":         sources,
        "rag_chunks_used": len(all_chunks),
    }
