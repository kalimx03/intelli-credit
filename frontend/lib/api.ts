import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({ baseURL: API_BASE });

export interface ExtractedField {
  value: number | boolean | string | null;
  confidence: number;
  evidence: string;
  flagged: boolean;
  flag_reason: string | null;
}

export interface FiveCsScore {
  character: number;
  capacity: number;
  capital: number;
  collateral: number;
  conditions: number;
  weighted_total: number;
}

export interface RuleLog {
  rule_name: string;
  category: string;
  triggered: boolean;
  impact: number;
  explanation: string;
  raw_value: unknown;
}

export interface ManagementInsightFlags {
  promoter_concern: boolean;
  succession_risk: boolean;
  sector_headwind: boolean;
  regulatory_concern: boolean;
  concentration_risk: boolean;
  expansion_risk: boolean;
  positive_management: boolean;
  raw_signals: string[];
}

export interface ScoringResult {
  five_cs: FiveCsScore;
  rule_log: RuleLog[];
  final_score: number;
  risk_band: string;
  decision: string;
  suggested_loan_limit: number;
  suggested_interest_rate: number;
  management_flags: ManagementInsightFlags;
}

export interface AnalysisResponse {
  analysis_id: string;
  company_name: string;
  extracted_financials: Record<string, ExtractedField>;
  scoring_result: ScoringResult;
  validation_warnings: string[];
  timestamp: string;
}

export async function analyzeDocument(formData: FormData): Promise<AnalysisResponse> {
  const res = await api.post('/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function generateCAM(analysisId: string): Promise<{ download_url: string }> {
  const res = await api.post(`/generate-cam/${analysisId}`);
  return res.data;
}

export async function getAnalysis(analysisId: string): Promise<AnalysisResponse> {
  const res = await api.get(`/analysis/${analysisId}`);
  return res.data;
}

export async function listAnalyses(): Promise<{ analyses: unknown[] }> {
  const res = await api.get('/analyses');
  return res.data;
}

export function getDownloadUrl(analysisId: string): string {
  return `${API_BASE}/download-cam/${analysisId}`;
}

export function formatINR(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'N/A';
  if (value >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)} Cr`;
  if (value >= 100_000) return `₹${(value / 100_000).toFixed(2)} L`;
  return `₹${value.toLocaleString('en-IN')}`;
}
