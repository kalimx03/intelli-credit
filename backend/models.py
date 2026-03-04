from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime


class ExtractedField(BaseModel):
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = ""
    flagged: bool = False
    flag_reason: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        """Coerce to float and clamp 0-1. Never crash on malformed LLM output."""
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("evidence", mode="before")
    @classmethod
    def coerce_evidence(cls, v: Any) -> str:
        """Evidence must always be a string; cap at 500 chars."""
        if v is None:
            return ""
        return str(v)[:500]

    @model_validator(mode="after")
    def flag_missing_evidence(self) -> "ExtractedField":
        """
        Anti-hallucination gate: a non-null value with no evidence is
        automatically flagged for human review. Value is NOT nullified —
        scoring continues but the field is marked as unverified.
        """
        if self.value is not None and not self.evidence.strip():
            self.flagged = True
            self.flag_reason = (
                (self.flag_reason or "") +
                " | No evidence for non-null value — hallucination risk"
            )
        return self


class ExtractedFinancials(BaseModel):
    # Revenue & Profitability
    revenue: Optional[ExtractedField] = None
    ebitda: Optional[ExtractedField] = None
    pat: Optional[ExtractedField] = None
    net_worth: Optional[ExtractedField] = None
    total_debt: Optional[ExtractedField] = None
    current_ratio: Optional[ExtractedField] = None
    debt_equity_ratio: Optional[ExtractedField] = None
    interest_coverage_ratio: Optional[ExtractedField] = None
    dscr: Optional[ExtractedField] = None

    # Compliance & Governance
    auditor_qualification: Optional[ExtractedField] = None
    gst_mismatch: Optional[ExtractedField] = None
    mca_filing_status: Optional[ExtractedField] = None
    rbi_regulatory_risk: Optional[ExtractedField] = None
    litigation_pending: Optional[ExtractedField] = None
    contingent_liabilities: Optional[ExtractedField] = None
    related_party_transactions: Optional[ExtractedField] = None

    # Business Profile
    years_in_operation: Optional[ExtractedField] = None
    promoter_experience_years: Optional[ExtractedField] = None
    industry_sector: Optional[ExtractedField] = None
    collateral_value: Optional[ExtractedField] = None
    collateral_type: Optional[ExtractedField] = None
    loan_amount_requested: Optional[ExtractedField] = None

    def safe_value(self, field: str) -> Any:
        """
        Null-safe value accessor used throughout the scoring engine.
        Returns None if field is absent, field is None, or value is None.
        Eliminates all AttributeError crashes in scoring.
        """
        obj = getattr(self, field, None)
        return None if obj is None else obj.value

    def safe_confidence(self, field: str) -> float:
        """Returns field confidence, or 0.0 if field is absent."""
        obj = getattr(self, field, None)
        return 0.0 if obj is None else obj.confidence


class RuleLog(BaseModel):
    rule_name: str
    category: str
    triggered: bool
    impact: float
    explanation: str
    raw_value: Optional[Any] = None


class FiveCsScore(BaseModel):
    character: float
    capacity: float
    capital: float
    collateral: float
    conditions: float
    weighted_total: float


class ManagementInsightFlags(BaseModel):
    promoter_concern: bool = False
    succession_risk: bool = False
    sector_headwind: bool = False
    regulatory_concern: bool = False
    concentration_risk: bool = False
    expansion_risk: bool = False
    positive_management: bool = False
    raw_signals: List[str] = []


class ScoringResult(BaseModel):
    five_cs: FiveCsScore
    rule_log: List[RuleLog]
    final_score: float
    risk_band: str   # Low / Moderate / High
    decision: str    # Approve / Conditional / Reject
    suggested_loan_limit: float
    suggested_interest_rate: float
    management_flags: ManagementInsightFlags


class AnalysisRequest(BaseModel):
    primary_insights: Optional[str] = None
    company_name: Optional[str] = None
    loan_amount_requested: Optional[float] = None


class AnalysisResponse(BaseModel):
    analysis_id: str
    company_name: Optional[str]
    extracted_financials: ExtractedFinancials
    scoring_result: ScoringResult
    validation_warnings: List[str]
    timestamp: datetime


class CAMRequest(BaseModel):
    analysis_id: str
