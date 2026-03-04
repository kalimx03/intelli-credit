from typing import List, Tuple
from models import (
    ExtractedFinancials, ManagementInsightFlags,
    ScoringResult, FiveCsScore, RuleLog,
)

# ---------------------------------------------------------------------------
# AUDIT FIX 5: Scoring engine is fully deterministic and independent of LLM.
# ALL values accessed via fin.safe_value() — never crashes on missing fields.
# ---------------------------------------------------------------------------


def _rule(name: str, category: str, triggered: bool, impact: float,
          explanation: str, raw_value=None) -> RuleLog:
    return RuleLog(
        rule_name=name,
        category=category,
        triggered=triggered,
        impact=impact if triggered else 0.0,
        explanation=explanation,
        raw_value=raw_value,
    )


# ---------------------------------------------------------------------------
# CHARACTER (25%)
# ---------------------------------------------------------------------------

def score_character(fin: ExtractedFinancials, mgmt: ManagementInsightFlags
                    ) -> Tuple[float, List[RuleLog]]:
    score = 100.0
    rules: List[RuleLog] = []

    # Auditor qualification
    aq = fin.safe_value("auditor_qualification")
    triggered = bool(aq) if aq is not None else False
    r = _rule("Auditor Qualification", "character", triggered, -20,
              "Auditor has raised qualifications or concerns — governance red flag.",
              raw_value=aq)
    rules.append(r)
    score += r.impact

    # Litigation pending
    lp = fin.safe_value("litigation_pending")
    triggered = bool(lp) if lp is not None else False
    r = _rule("Litigation Pending", "character", triggered, -15,
              "Active litigation detected — legal and reputational risk.",
              raw_value=lp)
    rules.append(r)
    score += r.impact

    # Related party transactions
    rpt = fin.safe_value("related_party_transactions")
    triggered = bool(rpt) if rpt is not None else False
    r = _rule("Related Party Transactions", "character", triggered, -10,
              "Significant RPTs detected — potential fund diversion risk.",
              raw_value=rpt)
    rules.append(r)
    score += r.impact

    # Years in operation
    yrs = fin.safe_value("years_in_operation")
    if yrs is not None:
        try:
            yrs = float(yrs)
            if yrs < 5:
                r = _rule("Years in Operation (<5)", "character", True, -15,
                          f"Business is only {yrs:.0f} years old — limited track record.",
                          raw_value=yrs)
            elif yrs < 10:
                r = _rule("Years in Operation (5-10)", "character", True, -5,
                          f"Business is {yrs:.0f} years old — moderate track record.",
                          raw_value=yrs)
            else:
                r = _rule("Years in Operation (>=10)", "character", False, 0,
                          f"Business has {yrs:.0f} years of operation — strong track record.",
                          raw_value=yrs)
            rules.append(r)
            score += r.impact
        except (TypeError, ValueError):
            pass

    # Management flags from primary insights
    if mgmt.promoter_concern:
        r = _rule("Promoter Concern", "character", True, -15,
                  "Promoter concerns flagged in management assessment.")
        rules.append(r)
        score += r.impact

    if mgmt.succession_risk:
        r = _rule("Succession Risk", "character", True, -8,
                  "Key-man dependency or unclear succession plan identified.")
        rules.append(r)
        score += r.impact

    if mgmt.positive_management:
        r = _rule("Positive Management", "character", True, 5,
                  "Strong professional management or governance noted.")
        rules.append(r)
        score += r.impact

    return max(0.0, min(100.0, score)), rules


# ---------------------------------------------------------------------------
# CAPACITY (30%)
# ---------------------------------------------------------------------------

def score_capacity(fin: ExtractedFinancials) -> Tuple[float, List[RuleLog]]:
    score = 100.0
    rules: List[RuleLog] = []

    # DSCR
    dscr = fin.safe_value("dscr")
    if dscr is not None:
        try:
            dscr = float(dscr)
            if dscr < 1.2:
                r = _rule("DSCR Critical (<1.2)", "capacity", True, -35,
                          f"DSCR of {dscr:.2f}x is critically low — debt repayment at risk.",
                          raw_value=dscr)
            elif dscr < 1.5:
                r = _rule("DSCR Marginal (1.2-1.5)", "capacity", True, -15,
                          f"DSCR of {dscr:.2f}x is marginal — limited repayment buffer.",
                          raw_value=dscr)
            else:
                r = _rule("DSCR Adequate (>=1.5)", "capacity", False, 0,
                          f"DSCR of {dscr:.2f}x is adequate.",
                          raw_value=dscr)
            rules.append(r)
            score += r.impact
        except (TypeError, ValueError):
            pass

    # Interest Coverage Ratio
    icr = fin.safe_value("interest_coverage_ratio")
    if icr is not None:
        try:
            icr = float(icr)
            if icr < 1.5:
                r = _rule("ICR Critical (<1.5)", "capacity", True, -25,
                          f"ICR of {icr:.2f}x — earnings barely cover interest obligations.",
                          raw_value=icr)
            elif icr < 3.0:
                r = _rule("ICR Marginal (1.5-3.0)", "capacity", True, -10,
                          f"ICR of {icr:.2f}x — moderate interest coverage.",
                          raw_value=icr)
            else:
                r = _rule("ICR Strong (>=3.0)", "capacity", False, 0,
                          f"ICR of {icr:.2f}x — strong interest coverage.",
                          raw_value=icr)
            rules.append(r)
            score += r.impact
        except (TypeError, ValueError):
            pass

    # EBITDA Margin
    rev = fin.safe_value("revenue")
    ebitda = fin.safe_value("ebitda")
    if rev is not None and ebitda is not None:
        try:
            rev_f = float(rev)
            ebitda_f = float(ebitda)
            if rev_f > 0:
                margin = (ebitda_f / rev_f) * 100
                if margin < 8:
                    r = _rule("EBITDA Margin Low (<8%)", "capacity", True, -20,
                              f"EBITDA margin of {margin:.1f}% — thin operating profitability.",
                              raw_value=round(margin, 2))
                elif margin < 15:
                    r = _rule("EBITDA Margin Moderate (8-15%)", "capacity", True, -10,
                              f"EBITDA margin of {margin:.1f}% — moderate profitability.",
                              raw_value=round(margin, 2))
                else:
                    r = _rule("EBITDA Margin Strong (>=15%)", "capacity", False, 0,
                              f"EBITDA margin of {margin:.1f}% — strong profitability.",
                              raw_value=round(margin, 2))
                rules.append(r)
                score += r.impact
        except (TypeError, ValueError):
            pass

    # Negative PAT
    pat = fin.safe_value("pat")
    if pat is not None:
        try:
            pat_f = float(pat)
            if pat_f < 0:
                r = _rule("Negative PAT", "capacity", True, -20,
                          f"Net loss of {pat_f:,.0f} — company is loss-making.",
                          raw_value=pat_f)
                rules.append(r)
                score += r.impact
        except (TypeError, ValueError):
            pass

    return max(0.0, min(100.0, score)), rules


# ---------------------------------------------------------------------------
# CAPITAL (20%)
# ---------------------------------------------------------------------------

def score_capital(fin: ExtractedFinancials) -> Tuple[float, List[RuleLog]]:
    score = 100.0
    rules: List[RuleLog] = []

    # Debt/Equity Ratio
    de = fin.safe_value("debt_equity_ratio")
    if de is not None:
        try:
            de_f = float(de)
            if de_f > 4.0:
                r = _rule("D/E Ratio High (>4x)", "capital", True, -30,
                          f"D/E ratio of {de_f:.2f}x — highly leveraged balance sheet.",
                          raw_value=de_f)
            elif de_f > 2.0:
                r = _rule("D/E Ratio Elevated (2-4x)", "capital", True, -15,
                          f"D/E ratio of {de_f:.2f}x — moderately leveraged.",
                          raw_value=de_f)
            else:
                r = _rule("D/E Ratio Healthy (<=2x)", "capital", False, 0,
                          f"D/E ratio of {de_f:.2f}x — conservative leverage.",
                          raw_value=de_f)
            rules.append(r)
            score += r.impact
        except (TypeError, ValueError):
            pass

    # Current Ratio
    cr = fin.safe_value("current_ratio")
    if cr is not None:
        try:
            cr_f = float(cr)
            if cr_f < 1.0:
                r = _rule("Current Ratio Critical (<1.0)", "capital", True, -25,
                          f"Current ratio of {cr_f:.2f}x — negative working capital risk.",
                          raw_value=cr_f)
            elif cr_f < 1.5:
                r = _rule("Current Ratio Tight (1.0-1.5)", "capital", True, -10,
                          f"Current ratio of {cr_f:.2f}x — limited liquidity buffer.",
                          raw_value=cr_f)
            else:
                r = _rule("Current Ratio Healthy (>=1.5)", "capital", False, 0,
                          f"Current ratio of {cr_f:.2f}x — adequate liquidity.",
                          raw_value=cr_f)
            rules.append(r)
            score += r.impact
        except (TypeError, ValueError):
            pass

    # Negative Net Worth
    nw = fin.safe_value("net_worth")
    if nw is not None:
        try:
            nw_f = float(nw)
            if nw_f < 0:
                r = _rule("Negative Net Worth", "capital", True, -30,
                          f"Net worth of {nw_f:,.0f} — technically insolvent.",
                          raw_value=nw_f)
                rules.append(r)
                score += r.impact
        except (TypeError, ValueError):
            pass

    # Contingent Liabilities vs Net Worth
    cl = fin.safe_value("contingent_liabilities")
    nw_v = fin.safe_value("net_worth")
    if cl is not None and nw_v is not None:
        try:
            cl_f = float(cl)
            nw_f = float(nw_v)
            if nw_f > 0 and cl_f > 0.5 * nw_f:
                r = _rule("Contingent Liabilities >50% NW", "capital", True, -15,
                          f"Contingent liabilities are {cl_f/nw_f:.0%} of net worth — elevated off-balance-sheet risk.",
                          raw_value=round(cl_f / nw_f, 2))
                rules.append(r)
                score += r.impact
        except (TypeError, ValueError):
            pass

    return max(0.0, min(100.0, score)), rules


# ---------------------------------------------------------------------------
# COLLATERAL (15%)
# ---------------------------------------------------------------------------

def score_collateral(fin: ExtractedFinancials) -> Tuple[float, List[RuleLog]]:
    rules: List[RuleLog] = []

    collateral_val = fin.safe_value("collateral_value")
    loan_amt = fin.safe_value("loan_amount_requested")
    collateral_type = fin.safe_value("collateral_type")

    # No collateral data at all
    if collateral_val is None:
        r = _rule("No Collateral Data", "collateral", True, -40,
                  "Collateral value not available — LTV cannot be computed.")
        rules.append(r)
        return 60.0, rules  # default base score

    try:
        cv_f = float(collateral_val)
        la_f = float(loan_amt) if loan_amt is not None else None

        # LTV-based scoring
        if la_f and la_f > 0:
            ltv = (la_f / cv_f) * 100 if cv_f > 0 else 999
            if ltv <= 60:
                score = 100.0
                r = _rule("LTV Conservative (<=60%)", "collateral", False, 0,
                          f"LTV of {ltv:.1f}% — strong collateral coverage.",
                          raw_value=round(ltv, 1))
            elif ltv <= 75:
                score = 80.0
                r = _rule("LTV Moderate (60-75%)", "collateral", True, -20,
                          f"LTV of {ltv:.1f}% — adequate but moderate collateral coverage.",
                          raw_value=round(ltv, 1))
            elif ltv <= 90:
                score = 55.0
                r = _rule("LTV High (75-90%)", "collateral", True, -45,
                          f"LTV of {ltv:.1f}% — thin collateral buffer.",
                          raw_value=round(ltv, 1))
            else:
                score = 30.0
                r = _rule("LTV Critical (>90%)", "collateral", True, -70,
                          f"LTV of {ltv:.1f}% — inadequate collateral coverage.",
                          raw_value=round(ltv, 1))
            rules.append(r)
        else:
            score = 70.0  # collateral present but no loan amount to compute LTV

        # Collateral type adjustment
        ct = str(collateral_type).lower() if collateral_type else ""
        if any(k in ct for k in ["immovable", "land", "property", "building", "real estate"]):
            r = _rule("Immovable Property Collateral", "collateral", True, 10,
                      "Immovable property as collateral — stronger security.",
                      raw_value=collateral_type)
            rules.append(r)
            score = min(100.0, score + 10)
        elif any(k in ct for k in ["current asset", "stock", "receivable", "debtors"]):
            r = _rule("Current Assets Collateral", "collateral", True, -10,
                      "Current assets as collateral — lower realisability.",
                      raw_value=collateral_type)
            rules.append(r)
            score = max(0.0, score - 10)

        return max(0.0, min(100.0, score)), rules

    except (TypeError, ValueError):
        r = _rule("Collateral Value Non-Numeric", "collateral", True, -40,
                  "Collateral value could not be parsed as a number.")
        rules.append(r)
        return 60.0, rules


# ---------------------------------------------------------------------------
# CONDITIONS (10%)
# ---------------------------------------------------------------------------

def score_conditions(fin: ExtractedFinancials, mgmt: ManagementInsightFlags
                     ) -> Tuple[float, List[RuleLog]]:
    score = 100.0
    rules: List[RuleLog] = []

    # GST mismatch
    gst = fin.safe_value("gst_mismatch")
    triggered = bool(gst) if gst is not None else False
    r = _rule("GST 2A/3B Mismatch", "conditions", triggered, -20,
              "GST 2A vs 3B mismatch detected — possible revenue suppression or ITC fraud.",
              raw_value=gst)
    rules.append(r)
    score += r.impact

    # RBI regulatory risk
    rbi = fin.safe_value("rbi_regulatory_risk")
    triggered = bool(rbi) if rbi is not None else False
    r = _rule("RBI Regulatory Risk", "conditions", triggered, -25,
              "RBI regulatory risk or NPA classification mentioned — systemic risk flag.",
              raw_value=rbi)
    rules.append(r)
    score += r.impact

    # MCA filing default
    mca = fin.safe_value("mca_filing_status")
    triggered = bool(mca) if mca is not None else False
    r = _rule("MCA Filing Default", "conditions", triggered, -10,
              "MCA filing delay or default detected — governance concern.",
              raw_value=mca)
    rules.append(r)
    score += r.impact

    # Management condition flags
    if mgmt.sector_headwind:
        r = _rule("Sector Headwind", "conditions", True, -15,
                  "Industry facing cyclical downturn, demand collapse, or adverse policy.")
        rules.append(r)
        score += r.impact

    if mgmt.regulatory_concern:
        r = _rule("Regulatory Concern", "conditions", True, -10,
                  "Pending regulatory action or license risk identified.")
        rules.append(r)
        score += r.impact

    if mgmt.concentration_risk:
        r = _rule("Concentration Risk", "conditions", True, -10,
                  "Revenue, customer, or supplier concentration in single entity.")
        rules.append(r)
        score += r.impact

    return max(0.0, min(100.0, score)), rules


# ---------------------------------------------------------------------------
# LOAN LIMIT & INTEREST RATE
# ---------------------------------------------------------------------------

def compute_loan_limit(revenue: float, score: float) -> float:
    """Deterministic loan limit = revenue * multiplier based on risk band."""
    if score >= 75:
        multiplier = 0.40
    elif score >= 50:
        multiplier = 0.25
    else:
        multiplier = 0.10
    return round(revenue * multiplier, 2)


def compute_interest_rate(score: float) -> float:
    """Deterministic risk-adjusted interest rate."""
    if score >= 80:
        return 8.5
    elif score >= 70:
        return 9.5
    elif score >= 60:
        return 10.5
    elif score >= 50:
        return 11.5
    else:
        return 13.5


# ---------------------------------------------------------------------------
# MAIN ORCHESTRATOR
# ---------------------------------------------------------------------------

def run_scoring(fin: ExtractedFinancials, mgmt: ManagementInsightFlags) -> ScoringResult:
    """
    Run the complete Five Cs scoring pipeline.
    All inputs from fin accessed via safe_value() — never crashes on null data.
    Returns a fully-populated ScoringResult.
    """
    # Score each pillar
    char_score, char_rules = score_character(fin, mgmt)
    capa_score, capa_rules = score_capacity(fin)
    cap_score,  cap_rules  = score_capital(fin)
    coll_score, coll_rules = score_collateral(fin)
    cond_score, cond_rules = score_conditions(fin, mgmt)

    # Weighted total
    weighted = (
        char_score * 0.25 +
        capa_score * 0.30 +
        cap_score  * 0.20 +
        coll_score * 0.15 +
        cond_score * 0.10
    )
    final_score = round(weighted, 2)

    # Risk band and decision
    if final_score >= 75:
        risk_band = "Low Risk"
        decision  = "Approve"
    elif final_score >= 50:
        risk_band = "Moderate Risk"
        decision  = "Conditional Approval"
    else:
        risk_band = "High Risk"
        decision  = "Reject"

    # Loan limit and rate
    revenue = fin.safe_value("revenue")
    try:
        rev_f = float(revenue) if revenue is not None else 0.0
    except (TypeError, ValueError):
        rev_f = 0.0

    loan_limit = compute_loan_limit(rev_f, final_score)
    interest_rate = compute_interest_rate(final_score)

    all_rules = char_rules + capa_rules + cap_rules + coll_rules + cond_rules

    return ScoringResult(
        five_cs=FiveCsScore(
            character=round(char_score, 2),
            capacity=round(capa_score, 2),
            capital=round(cap_score, 2),
            collateral=round(coll_score, 2),
            conditions=round(cond_score, 2),
            weighted_total=final_score,
        ),
        rule_log=all_rules,
        final_score=final_score,
        risk_band=risk_band,
        decision=decision,
        suggested_loan_limit=loan_limit,
        suggested_interest_rate=interest_rate,
        management_flags=mgmt,
    )
