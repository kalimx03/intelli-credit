import os
import re
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER

# ---------------------------------------------------------------------------
# AUDIT FIX 9: CAM generation never breaks on null/missing financial fields.
# Every access is null-safe. ReportLab XML characters are escaped.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

DARK_BLUE  = colors.HexColor("#1a2744")
MID_BLUE   = colors.HexColor("#2c4a8c")
LIGHT_BLUE = colors.HexColor("#e8edf7")
ACCENT     = colors.HexColor("#c8392b")
GREEN      = colors.HexColor("#1a7a4a")
ORANGE     = colors.HexColor("#d4700a")
TEXT_DARK  = colors.HexColor("#1a1a2e")
GRAY       = colors.HexColor("#666677")

_XML_ESCAPE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def _ss(v: object, maxlen: int = 300) -> str:
    """Safe string: escape XML chars, cap length, never None."""
    if v is None:
        return "N/A"
    return str(v)[:maxlen].translate(_XML_ESCAPE)


def _sn(text: object, maxlen: int = 2000) -> str:
    """Safe narrative: strip control chars, escape XML, cap length."""
    if not text:
        return "Not available."
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text))
    return cleaned[:maxlen].translate(_XML_ESCAPE)


def _sf(v: object):
    """Safe float: return float or None, never raise."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _format_inr(value: object) -> str:
    v = _sf(value)
    if v is None:
        return "N/A"
    if v >= 10_000_000:
        return f"Rs {v / 10_000_000:.2f} Cr"
    if v >= 100_000:
        return f"Rs {v / 100_000:.2f} L"
    return f"Rs {v:,.0f}"


def _styles() -> dict:
    getSampleStyleSheet()
    return {
        "title":           ParagraphStyle("ic_title",    fontSize=20, textColor=colors.white,
                                          fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4),
        "subtitle":        ParagraphStyle("ic_subtitle", fontSize=11, textColor=LIGHT_BLUE,
                                          fontName="Helvetica", alignment=TA_CENTER, spaceAfter=2),
        "h1":              ParagraphStyle("ic_h1",       fontSize=13, textColor=colors.white,
                                          fontName="Helvetica-Bold", spaceAfter=6),
        "body":            ParagraphStyle("ic_body",     fontSize=9,  textColor=TEXT_DARK,
                                          fontName="Helvetica", leading=14, spaceAfter=6),
        "decision_approve":ParagraphStyle("ic_da",       fontSize=16, textColor=GREEN,
                                          fontName="Helvetica-Bold", alignment=TA_CENTER),
        "decision_reject": ParagraphStyle("ic_dr",       fontSize=16, textColor=ACCENT,
                                          fontName="Helvetica-Bold", alignment=TA_CENTER),
        "decision_cond":   ParagraphStyle("ic_dc",       fontSize=16, textColor=ORANGE,
                                          fontName="Helvetica-Bold", alignment=TA_CENTER),
        "score_sub":       ParagraphStyle("ic_ss",       fontSize=10, textColor=GRAY,
                                          alignment=TA_CENTER),
        "footer":          ParagraphStyle("ic_footer",   fontSize=7,  textColor=GRAY,
                                          alignment=TA_CENTER),
    }


def _section_header(title: str, styles: dict) -> list:
    return [
        Table(
            [[Paragraph(_ss(title, 100), styles["h1"])]],
            colWidths=[17 * cm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), MID_BLUE),
                ("PADDING",    (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Spacer(1, 0.2 * cm),
    ]


def generate_cam_pdf(
    analysis_id: str,
    company_name: str,
    financials: dict,
    scoring: dict,
    narratives: dict,
    output_dir: str = "cam_reports",
) -> str:
    """
    Generate a ReportLab PDF CAM. Every financials/scoring access is null-safe.
    Returns path to the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r"[^\w\s-]", "", company_name).strip().replace(" ", "_")[:60]
    filename = os.path.join(output_dir, f"CAM_{safe_name}_{analysis_id[:8]}.pdf")

    doc = SimpleDocTemplate(
        filename, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = _styles()
    story = []

    # ---- Header ------------------------------------------------------------
    story.append(Table(
        [[item] for item in [
            Paragraph("INTELLI-CREDIT", styles["title"]),
            Paragraph("Credit Appraisal Memorandum", styles["subtitle"]),
            Paragraph(_ss(company_name, 120), styles["subtitle"]),
            Paragraph(
                f"Date: {datetime.now().strftime('%d %B %Y')} | "
                f"ID: {_ss(analysis_id[:12])}",
                styles["subtitle"],
            ),
        ]],
        colWidths=[17 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("PADDING",    (0, 0), (-1, -1), 6),
        ]),
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ---- Decision Banner ---------------------------------------------------
    decision  = _ss(scoring.get("decision") or "N/A", 50)
    score     = _sf(scoring.get("final_score")) or 0.0
    risk_band = _ss(scoring.get("risk_band") or "N/A", 50)

    dec_style = (
        styles["decision_approve"] if decision == "Approve"
        else styles["decision_reject"] if decision == "Reject"
        else styles["decision_cond"]
    )
    dec_color = GREEN if decision == "Approve" else (ACCENT if decision == "Reject" else ORANGE)

    story.append(Table(
        [
            [Paragraph(f"CREDIT DECISION: {decision.upper()}", dec_style)],
            [Paragraph(f"Final Score: {score:.1f}/100 | {risk_band}", styles["score_sub"])],
        ],
        colWidths=[17 * cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fc")),
            ("BOX",        (0, 0), (-1, -1), 2, dec_color),
            ("PADDING",    (0, 0), (-1, -1), 10),
        ]),
    ))
    story.append(Spacer(1, 0.4 * cm))

    # ---- Narrative Sections 1-3 --------------------------------------------
    for sec_title, nar_key in [
        ("1. EXECUTIVE SUMMARY",  "executive_summary"),
        ("2. COMPANY PROFILE",    "company_profile"),
        ("3. FINANCIAL ANALYSIS", "financial_analysis"),
    ]:
        story += _section_header(sec_title, styles)
        story.append(Paragraph(_sn(narratives.get(nar_key)), styles["body"]))
        story.append(Spacer(1, 0.3 * cm))

    # ---- Financial Metrics Table -------------------------------------------
    fin_rows = []

    def _add_row(label: str, field: str, is_ratio: bool = False) -> None:
        f = financials.get(field)
        if not isinstance(f, dict):
            return
        v = _sf(f.get("value"))
        if v is None:
            return
        conf = _sf(f.get("confidence")) or 0.0
        evid = _ss(f.get("evidence") or "", 55)
        display = f"{v:.2f}x" if is_ratio else _format_inr(v)
        fin_rows.append([label, display, f"{conf:.0%}", evid])

    for label, field, ratio in [
        ("Revenue",       "revenue",               False),
        ("EBITDA",        "ebitda",                False),
        ("PAT",           "pat",                   False),
        ("Net Worth",     "net_worth",             False),
        ("Total Debt",    "total_debt",            False),
        ("Current Ratio", "current_ratio",         True),
        ("D/E Ratio",     "debt_equity_ratio",     True),
        ("ICR",           "interest_coverage_ratio", True),
        ("DSCR",          "dscr",                  True),
    ]:
        _add_row(label, field, ratio)

    if fin_rows:
        fin_table = Table(
            [["Metric", "Value", "Confidence", "Evidence"]] + fin_rows,
            colWidths=[3.5*cm, 3*cm, 2.5*cm, 8*cm],
        )
        fin_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  DARK_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LIGHT_BLUE]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#ccccdd")),
            ("PADDING",       (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(fin_table)
    else:
        story.append(Paragraph(
            "No financial metrics were extracted from the document.", styles["body"]
        ))
    story.append(Spacer(1, 0.3 * cm))

    # ---- Narrative Sections 4-6 --------------------------------------------
    for sec_title, nar_key in [
        ("4. COMPLIANCE &amp; GST REVIEW",       "compliance_gst_review"),
        ("5. LITIGATION &amp; LEGAL RISK",        "litigation_legal_risk"),
        ("6. SECTOR &amp; REGULATORY CONDITIONS", "sector_conditions"),
    ]:
        story += _section_header(sec_title, styles)
        story.append(Paragraph(_sn(narratives.get(nar_key)), styles["body"]))
        story.append(Spacer(1, 0.3 * cm))

    # ---- Section 7: Five Cs Table ------------------------------------------
    story += _section_header("7. FIVE Cs BREAKDOWN", styles)
    five_cs = scoring.get("five_cs") or {}
    cs_data = [["Pillar", "Weight", "Score (/100)", "Weighted Score"]]
    for label, key, weight in [
        ("Character",  "character",  0.25),
        ("Capacity",   "capacity",   0.30),
        ("Capital",    "capital",    0.20),
        ("Collateral", "collateral", 0.15),
        ("Conditions", "conditions", 0.10),
    ]:
        s = _sf(five_cs.get(key))
        cs_data.append([
            label,
            f"{int(weight * 100)}%",
            f"{s:.1f}" if s is not None else "N/A",
            f"{s * weight:.1f}" if s is not None else "N/A",
        ])
    wt = _sf(five_cs.get("weighted_total"))
    cs_data.append([
        "TOTAL WEIGHTED SCORE", "100%", "",
        f"{wt:.1f}" if wt is not None else "N/A",
    ])
    cs_table = Table(cs_data, colWidths=[5*cm, 3*cm, 5*cm, 4*cm])
    cs_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),  DARK_BLUE),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, -1), (-1, -1), LIGHT_BLUE),
        ("FONTSIZE",      (0, 0),  (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1),  (-1, -2), [colors.white, LIGHT_BLUE]),
        ("GRID",          (0, 0),  (-1, -1), 0.5, colors.HexColor("#ccccdd")),
        ("PADDING",       (0, 0),  (-1, -1), 7),
        ("ALIGN",         (1, 0),  (-1, -1), "CENTER"),
    ]))
    story.append(cs_table)
    story.append(Spacer(1, 0.3 * cm))

    # ---- Section 8: Risk Trigger Log ---------------------------------------
    story += _section_header("8. RISK TRIGGER LOG", styles)
    rule_log = scoring.get("rule_log") or []
    triggered = [r for r in rule_log if isinstance(r, dict) and r.get("triggered")]
    if triggered:
        rule_data = [["Rule", "Category", "Impact", "Explanation"]]
        for rule in triggered:
            impact = _sf(rule.get("impact")) or 0.0
            rule_data.append([
                _ss(rule.get("rule_name") or "", 40),
                _ss((rule.get("category") or "").upper(), 15),
                f"{impact:+.0f}",
                _ss(rule.get("explanation") or "", 70),
            ])
        rule_table = Table(rule_data, colWidths=[4.5*cm, 2.5*cm, 2*cm, 8*cm])
        rule_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0),  (-1, 0),  DARK_BLUE),
            ("TEXTCOLOR",     (0, 0),  (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0),  (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0),  (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 1),  (-1, -1), [colors.HexColor("#fff8f8"), colors.HexColor("#fff3f3")]),
            ("GRID",          (0, 0),  (-1, -1), 0.3, colors.HexColor("#ddcccc")),
            ("TEXTCOLOR",     (2, 1),  (2, -1),  ACCENT),
            ("FONTNAME",      (2, 1),  (2, -1),  "Helvetica-Bold"),
            ("PADDING",       (0, 0),  (-1, -1), 5),
        ]))
        story.append(rule_table)
    else:
        story.append(Paragraph(
            "No risk triggers fired. All metrics within acceptable bands.", styles["body"]
        ))
    story.append(Spacer(1, 0.3 * cm))

    # ---- Section 9: Final Decision -----------------------------------------
    story += _section_header("9. FINAL DECISION &amp; RECOMMENDATION", styles)
    loan_limit = _sf(scoring.get("suggested_loan_limit"))
    rate       = _sf(scoring.get("suggested_interest_rate"))
    rec_data = [
        ["Credit Decision",      _ss(decision, 30)],
        ["Final Score",          f"{score:.1f} / 100"],
        ["Risk Classification",  _ss(risk_band, 40)],
        ["Suggested Loan Limit", _format_inr(loan_limit)],
        ["Suggested Rate",       f"{rate:.2f}% p.a." if rate is not None else "N/A"],
    ]
    rec_table = Table(rec_data, colWidths=[6*cm, 11*cm])
    rec_table.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1,-1), 10),
        ("BACKGROUND",(0, 0), (0, -1), LIGHT_BLUE),
        ("GRID",      (0, 0), (-1,-1), 0.5, colors.HexColor("#ccccdd")),
        ("PADDING",   (0, 0), (-1,-1), 8),
        ("TEXTCOLOR", (1, 0), (1,  0), dec_color),
        ("FONTNAME",  (1, 0), (1,  0), "Helvetica-Bold"),
        ("FONTSIZE",  (1, 0), (1,  0), 12),
    ]))
    story.append(rec_table)
    story.append(Spacer(1, 0.3 * cm))

    # ---- Section 10: Justification -----------------------------------------
    story += _section_header("10. JUSTIFICATION NARRATIVE", styles)
    story.append(Paragraph(_sn(narratives.get("justification_narrative")), styles["body"]))
    story.append(Spacer(1, 0.5 * cm))

    # ---- Footer ------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_BLUE))
    story.append(Paragraph(
        "This CAM is system-generated by Intelli-Credit. All credit decisions are "
        "deterministic and rule-based. LLM is used only for data extraction and "
        "narrative generation. Final credit decision rests with the sanctioning authority.",
        styles["footer"],
    ))

    try:
        doc.build(story)
    except Exception as e:
        logger.error("ReportLab doc.build() failed: %s", e, exc_info=True)
        raise RuntimeError(f"PDF rendering failed: {e}") from e

    logger.info("CAM PDF generated: %s", filename)
    return filename
