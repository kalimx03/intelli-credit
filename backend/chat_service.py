import logging
from typing import List, Dict, Any, Optional
from rag_engine import retrieve_context, format_context_for_prompt, get_historical_context

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are Intelli-Credit's AI credit analyst assistant for Indian banking.
You help bank officers understand credit appraisal reports and Indian banking regulations.
You have three sources of information:
1. The ANALYSIS DATA — actual extracted financials, Five Cs scores, and triggered risk rules
2. REGULATORY CONTEXT — relevant RBI/GST/MCA guidelines retrieved from the knowledge base
3. WEB SEARCH RESULTS — live news about the company, promoters, sector headwinds

Your rules:
- Always cite specific numbers from the analysis (e.g. "DSCR of 1.15x", "D/E ratio 3.8x")
- When citing regulations, say which guideline it comes from (e.g. "As per RBI IRACP norms...")
- When citing web results, mention the source
- If something is not in the analysis data, say "the analysis does not contain this information"
- Never invent financial figures
- Keep answers focused and under 300 words unless the question requires more
- Use plain language — the audience is credit officers, not data scientists
"""

def _web_search(query: str, max_results: int = 3) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No web results found."
        lines = []
        for r in results:
            lines.append(f"SOURCE: {r.get('href', '')}")
            lines.append(f"TITLE: {r.get('title', '')}")
            lines.append(f"SNIPPET: {r.get('body', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Web search failed: %s", e)
        return "Web search temporarily unavailable."

def _should_search_web(question: str) -> bool:
    keywords = [
        "news", "recent", "latest", "promoter", "litigation", "court", "fraud",
        "sector", "industry", "headwind", "regulation", "rbi", "sebi", "mca",
        "npa", "default", "bankrupt", "lawsuit", "scam", "controversy"
    ]
    q = question.lower()
    return any(k in q for k in keywords)

def _build_analysis_summary(data: Dict[str, Any]) -> str:
    fin     = data.get("extracted_financials", {})
    scoring = data.get("scoring_result", {})
    warns   = data.get("validation_warnings", [])

    def fv(field: str):
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
        ("Auditor Qualification", "auditor_qualification"),
        ("GST 2A/3B Mismatch",   "gst_mismatch"),
        ("MCA Filing Default",    "mca_filing_status"),
        ("RBI Regulatory Risk",   "rbi_regulatory_risk"),
        ("Litigation Pending",    "litigation_pending"),
        ("Related Party Transactions", "related_party_transactions"),
    ]
    lines.append("")
    lines.append("COMPLIANCE FLAGS:")
    for label, field in compliance_fields:
        v = fv(field)
        if v is not None:
            lines.append(f"  {label}: {'YES' if v else 'No'}")

    rule_log = scoring.get("rule_log", [])
    triggered = [r for r in rule_log if r.get("triggered")]
    if triggered:
        lines.append("")
        lines.append(f"RISK RULES TRIGGERED ({len(triggered)}):")
        for r in triggered:
            lines.append(f"  [{r.get('category','').upper()}] {r.get('rule_name','')} impact: {r.get('impact', 0):+.0f}")

    return "\n".join(lines)


def answer_question(
    question: str,
    analysis_data: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    import os
    from groq import Groq

    all_chunks = []
    try:
        reg_chunks = retrieve_context(question, n_results=3)
        score = analysis_data.get("scoring_result", {}).get("final_score", 50)
        sector = None
        fin = analysis_data.get("extracted_financials", {})
        sf = fin.get("industry_sector", {})
        if isinstance(sf, dict):
            sector = sf.get("value")
        hist_chunks = get_historical_context(score, sector)
        seen = set()
        for chunk in reg_chunks + hist_chunks:
            if chunk["title"] not in seen:
                all_chunks.append(chunk)
                seen.add(chunk["title"])
        rag_context = format_context_for_prompt(all_chunks[:4])
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)
        rag_context = "Regulatory context temporarily unavailable."

    # Web search for news/litigation/sector queries
    web_context = ""
    if _should_search_web(question):
        company = analysis_data.get("company_name", "")
        search_query = f"{company} {question}"
        logger.info("Web search triggered for: %s", search_query)
        web_context = _web_search(search_query)

    analysis_summary = _build_analysis_summary(analysis_data)

    messages = []
    if conversation_history:
        for turn in conversation_history[-6:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": str(turn["content"])})

    user_content = f"ANALYSIS DATA:\n{analysis_summary}\n\nREGULATORY CONTEXT:\n{rag_context}"
    if web_context:
        user_content += f"\n\nLIVE WEB SEARCH RESULTS:\n{web_context}"
    user_content += f"\n\nQUESTION: {question}"

    messages.append({"role": "user", "content": user_content})

    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + messages,
            max_tokens=1024,
            temperature=0.1,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        logger.error("Chat LLM call failed: %s", e)
        answer = f"I encountered an error: {e}. Please try again."

    sources = [
        {"title": c["title"], "category": c["category"], "relevance": c["score"]}
        for c in all_chunks[:4]
    ]

    return {
        "answer": answer,
        "sources": sources,
        "rag_chunks_used": len(all_chunks),
        "web_search_used": bool(web_context),
    }