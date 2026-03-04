'use client';

import { useEffect, useState, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { getAnalysis, generateCAM, getDownloadUrl, formatINR, AnalysisResponse, api } from '@/lib/api';
import { CheckCircle, AlertTriangle, Download, FileText, Send, Bot, User, BookOpen, Zap } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface ChatSource {
  title: string;
  category: string;
  relevance: number;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
}

// ─────────────────────────────────────────────────────────────────────────────
// RAG Chat Panel
// ─────────────────────────────────────────────────────────────────────────────

function ChatPanel({ analysisId, companyName }: { analysisId: string; companyName: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: `Hi! I'm your RAG-powered credit analyst for **${companyName}**.\n\nI have access to:\n• This full credit analysis (scores, financials, risk rules)\n• RBI guidelines, GST regulations, MCA norms\n• Historical credit decision patterns\n\nAsk me anything about this analysis or Indian banking regulations.`,
  }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: q }]);
    setLoading(true);
    try {
      const history = messages.slice(-6).map(m => ({ role: m.role, content: m.content }));
      const res = await api.post(`/chat/${analysisId}`, { question: q, history });
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.data.answer,
        sources: res.data.sources,
      }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error contacting the AI. Is the backend running?' }]);
    } finally {
      setLoading(false);
    }
  };

  const quickQuestions = [
    "Why was this credit decision made?",
    "What do RBI norms say about this DSCR?",
    "Are the D/E ratio and leverage acceptable?",
    "What are the biggest risk flags here?",
  ];

  const categoryColors: Record<string, string> = {
    rbi_guidelines:       '#3b82f6',
    gst_regulations:      '#f59e0b',
    mca_regulations:      '#8b5cf6',
    credit_norms:         '#10b981',
    sector_intelligence:  '#f97316',
    governance:           '#ef4444',
    historical_decisions: '#6366f1',
    fraud_prevention:     '#dc2626',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '540px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '0.875rem 1.25rem', borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'rgba(79,142,247,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Bot size={17} style={{ color: '#4f8ef7' }} />
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: '0.88rem' }}>RAG Credit Analyst</div>
            <div style={{ color: '#8899cc', fontSize: '0.72rem' }}>ChromaDB · all-MiniLM-L6-v2 · Claude · RBI/GST/MCA Knowledge Base</div>
          </div>
        </div>
        <div style={{ background: 'rgba(79,142,247,0.15)', border: '1px solid rgba(79,142,247,0.3)', borderRadius: '20px', padding: '0.2rem 0.6rem', fontSize: '0.7rem', color: '#7baeff', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          <Zap size={9} /> RAG Active
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', gap: '0.6rem', alignItems: 'flex-start' }}>
            {/* Avatar */}
            <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: msg.role === 'user' ? '#2c5fd4' : 'rgba(79,142,247,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
              {msg.role === 'user'
                ? <User size={13} style={{ color: '#fff' }} />
                : <Bot  size={13} style={{ color: '#4f8ef7' }} />}
            </div>
            <div style={{ maxWidth: '78%' }}>
              {/* Bubble */}
              <div style={{
                background: msg.role === 'user' ? '#2c5fd4' : 'rgba(255,255,255,0.07)',
                border: msg.role === 'assistant' ? '1px solid rgba(255,255,255,0.08)' : 'none',
                borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                padding: '0.65rem 0.95rem',
                color: '#e8eef8',
                fontSize: '0.86rem',
                lineHeight: 1.55,
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
              {/* Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  {msg.sources.slice(0, 3).map((s, si) => (
                    <span key={si} style={{
                      fontSize: '0.68rem',
                      background: 'rgba(0,0,0,0.25)',
                      color: '#aabbdd',
                      padding: '0.18rem 0.55rem',
                      borderRadius: '10px',
                      border: `1px solid ${categoryColors[s.category] || '#555'}44`,
                      display: 'flex', alignItems: 'center', gap: '0.3rem',
                    }}>
                      <BookOpen size={9} style={{ color: categoryColors[s.category] || '#888' }} />
                      {s.title.length > 32 ? s.title.slice(0, 32) + '…' : s.title}
                      <span style={{ color: '#667788' }}>· {(s.relevance * 100).toFixed(0)}%</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(79,142,247,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={13} style={{ color: '#4f8ef7' }} />
            </div>
            <div style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px', padding: '0.65rem 1rem' }}>
              <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#4f8ef7', opacity: 0.7, animation: `bounce${i} 1.2s ${i*0.2}s infinite ease-in-out` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick questions (shown only at start) */}
      {messages.length <= 1 && (
        <div style={{ padding: '0 1rem 0.6rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          {quickQuestions.map((q, i) => (
            <button key={i} onClick={() => setInput(q)} style={{ fontSize: '0.73rem', background: 'rgba(79,142,247,0.08)', border: '1px solid rgba(79,142,247,0.2)', borderRadius: '20px', padding: '0.3rem 0.75rem', color: '#7baeff', cursor: 'pointer', transition: 'all 0.15s' }}>
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', gap: '0.6rem' }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask about this analysis or RBI/GST/MCA regulations..."
          style={{ flex: 1, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', padding: '0.6rem 0.9rem', color: '#e8eef8', fontSize: '0.86rem', outline: 'none' }}
        />
        <button onClick={send} disabled={loading || !input.trim()} style={{ padding: '0.6rem 1rem', background: (loading || !input.trim()) ? 'rgba(79,142,247,0.25)' : '#2c5fd4', border: 'none', borderRadius: '10px', cursor: (loading || !input.trim()) ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}>
          <Send size={15} style={{ color: '#fff' }} />
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard
// ─────────────────────────────────────────────────────────────────────────────

type Tab = 'overview' | 'metrics' | 'rules' | 'warnings' | 'chat';

function DashboardContent() {
  const params      = useSearchParams();
  const analysisId  = params.get('id') || '';
  const [data, setData]         = useState<AnalysisResponse | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [tab, setTab]           = useState<Tab>('overview');
  const [camLoading, setCamLoading] = useState(false);
  const [camReady, setCamReady]     = useState(false);

  useEffect(() => {
    if (!analysisId) { setError('No analysis ID in URL.'); setLoading(false); return; }
    getAnalysis(analysisId)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError('Could not load analysis. Is the backend running?'); setLoading(false); });
  }, [analysisId]);

  if (loading) return (
    <div style={centerStyle}>
      <div style={spinnerStyle} />
      <p style={{ color: '#8899cc', marginTop: '1rem', fontSize: '0.9rem' }}>Loading analysis...</p>
    </div>
  );
  if (error || !data) return (
    <div style={centerStyle}>
      <p style={{ color: '#f87171', fontSize: '1rem' }}>{error || 'Analysis not found.'}</p>
    </div>
  );

  const s   = data.scoring_result;
  const fin = data.extracted_financials;
  const warns = data.validation_warnings;

  const decColor = s.decision === 'Approve' ? '#4ade80' : s.decision === 'Reject' ? '#f87171' : '#fbbf24';
  const decBg    = s.decision === 'Approve' ? 'rgba(74,222,128,0.08)' : s.decision === 'Reject' ? 'rgba(248,113,113,0.08)' : 'rgba(251,191,36,0.08)';

  const handleGenerateCAM = async () => {
    setCamLoading(true);
    try { await generateCAM(analysisId); setCamReady(true); }
    catch { alert('CAM generation failed. Check backend logs.'); }
    finally { setCamLoading(false); }
  };

  return (
    <main style={{ minHeight: '100vh', background: '#0c1220', fontFamily: "'IBM Plex Sans', sans-serif", color: '#e8eef8', padding: '2rem' }}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes bounce0 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }
        @keyframes bounce1 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }
        @keyframes bounce2 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }
      `}</style>

      <div style={{ maxWidth: '1100px', margin: '0 auto' }}>

        {/* ── Header ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.75rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, margin: 0 }}>
              Intelli<span style={{ color: '#4f8ef7' }}>Credit</span>
            </h1>
            <p style={{ color: '#6677aa', margin: '0.3rem 0 0', fontSize: '0.88rem' }}>
              {data.company_name} · {new Date(data.timestamp).toLocaleString('en-IN')}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
            <button onClick={() => setTab('chat')} style={{ ...btnStyle('#1a2f50'), border: '1px solid rgba(79,142,247,0.35)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Bot size={14} /> AI Analyst Chat
            </button>
            {!camReady
              ? <button onClick={handleGenerateCAM} disabled={camLoading} style={{ ...btnStyle('#2c5fd4'), display: 'flex', alignItems: 'center', gap: '0.4rem', opacity: camLoading ? 0.6 : 1 }}>
                  <FileText size={14} /> {camLoading ? 'Generating…' : 'Generate CAM PDF'}
                </button>
              : <a href={getDownloadUrl(analysisId)} target="_blank" rel="noreferrer" style={{ ...btnStyle('#1a7a4a'), textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Download size={14} /> Download CAM
                </a>
            }
          </div>
        </div>

        {/* ── Decision + Score ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.5rem' }}>
          <div style={{ background: decBg, border: `2px solid ${decColor}40`, borderRadius: '16px', padding: '1.5rem', textAlign: 'center' }}>
            <div style={{ fontSize: '0.72rem', color: '#667799', textTransform: 'uppercase', letterSpacing: '1.5px', marginBottom: '0.5rem' }}>Credit Decision</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: decColor }}>{s.decision.toUpperCase()}</div>
            <div style={{ color: '#667799', fontSize: '0.85rem', marginTop: '0.3rem' }}>{s.risk_band}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '16px', padding: '1.5rem' }}>
            <div style={{ fontSize: '0.72rem', color: '#667799', textTransform: 'uppercase', letterSpacing: '1.5px', marginBottom: '0.6rem' }}>Final Score</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
              <span style={{ fontSize: '2.4rem', fontWeight: 800, color: decColor }}>{s.final_score.toFixed(1)}</span>
              <span style={{ color: '#667799', fontSize: '1rem' }}>/100</span>
            </div>
            <div style={{ marginTop: '0.8rem', background: 'rgba(255,255,255,0.08)', borderRadius: '6px', height: '7px' }}>
              <div style={{ width: `${Math.min(100, s.final_score)}%`, height: '100%', background: decColor, borderRadius: '6px', transition: 'width 1s ease' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.5rem', fontSize: '0.75rem', color: '#667799' }}>
              <span>Loan Limit: {formatINR(s.suggested_loan_limit)}</span>
              <span>Rate: {s.suggested_interest_rate}% p.a.</span>
            </div>
          </div>
        </div>

        {/* ── Tabs ── */}
        <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '1.25rem', borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '0.6rem', flexWrap: 'wrap' }}>
          {(['overview', 'metrics', 'rules', 'warnings', 'chat'] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '0.45rem 1.05rem', border: 'none', borderRadius: '8px',
              cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem', transition: 'all 0.15s',
              background: tab === t ? (t === 'chat' ? '#1a2f50' : '#253868') : 'transparent',
              color: tab === t ? '#fff' : '#667799',
              outline: tab === t ? `1px solid ${t === 'chat' ? 'rgba(79,142,247,0.4)' : 'rgba(79,142,247,0.25)'}` : 'none',
            }}>
              {t === 'chat' ? <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}><Bot size={13} />AI Chat</span> : t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'warnings' && warns.length > 0 &&
                <span style={{ marginLeft: '0.4rem', background: '#c8392b', borderRadius: '10px', padding: '0.05rem 0.45rem', fontSize: '0.7rem' }}>{warns.length}</span>}
            </button>
          ))}
        </div>

        {/* ── Overview: Five Cs ── */}
        {tab === 'overview' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem' }}>
            {([
              ['Character',  'character',  0.25],
              ['Capacity',   'capacity',   0.30],
              ['Capital',    'capital',    0.20],
              ['Collateral', 'collateral', 0.15],
              ['Conditions', 'conditions', 0.10],
            ] as [string, keyof typeof s.five_cs, number][]).map(([label, key, weight]) => {
              const val = s.five_cs[key] as number;
              const c = val >= 70 ? '#4ade80' : val >= 50 ? '#fbbf24' : '#f87171';
              return (
                <div key={key} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '1.25rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.74rem', color: '#667799', marginBottom: '0.5rem' }}>{label}</div>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: c }}>{val.toFixed(0)}</div>
                  <div style={{ fontSize: '0.68rem', color: '#556688', marginTop: '0.2rem' }}>Weight {(weight*100).toFixed(0)}%</div>
                  <div style={{ marginTop: '0.7rem', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', height: '5px' }}>
                    <div style={{ width: `${val}%`, height: '100%', background: c, borderRadius: '4px' }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Metrics ── */}
        {tab === 'metrics' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.9rem' }}>
            {Object.entries(fin).map(([key, field]) => {
              const f = field as { value: unknown; confidence: number; evidence: string; flagged: boolean };
              if (!f || f.value === null || f.value === undefined) return null;
              return (
                <div key={key} style={{ background: 'rgba(255,255,255,0.04)', border: `1px solid ${f.flagged ? 'rgba(248,113,113,0.3)' : 'rgba(255,255,255,0.07)'}`, borderRadius: '10px', padding: '0.9rem 1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: '#667799', fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{key.replace(/_/g, ' ')}</span>
                    {f.flagged ? <AlertTriangle size={13} style={{ color: '#fbbf24' }} /> : <CheckCircle size={13} style={{ color: '#4ade80' }} />}
                  </div>
                  <div style={{ fontSize: '1.05rem', fontWeight: 700, marginTop: '0.3rem', color: f.flagged ? '#fbbf24' : '#e8eef8' }}>
                    {typeof f.value === 'boolean' ? (f.value ? 'Yes ⚠️' : 'No ✓') :
                     typeof f.value === 'number'  ? (f.value > 100000 ? formatINR(f.value) : f.value.toFixed(2)) :
                     String(f.value)}
                  </div>
                  <div style={{ marginTop: '0.45rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)', borderRadius: '3px', height: '4px' }}>
                      <div style={{ width: `${f.confidence * 100}%`, height: '100%', borderRadius: '3px', background: f.confidence >= 0.8 ? '#4ade80' : f.confidence >= 0.6 ? '#fbbf24' : '#f87171' }} />
                    </div>
                    <span style={{ fontSize: '0.7rem', color: '#556688' }}>{(f.confidence * 100).toFixed(0)}% conf</span>
                  </div>
                  {f.evidence && <div style={{ fontSize: '0.71rem', color: '#556688', marginTop: '0.35rem', fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>"{f.evidence}"</div>}
                </div>
              );
            })}
          </div>
        )}

        {/* ── Rules ── */}
        {tab === 'rules' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
            {s.rule_log.filter(r => r.triggered).length === 0 && (
              <div style={{ textAlign: 'center', color: '#4ade80', padding: '2rem', fontSize: '0.9rem' }}>✓ No risk triggers fired — all metrics within acceptable bounds.</div>
            )}
            {s.rule_log.filter(r => r.triggered).map((rule, i) => (
              <div key={i} style={{ background: 'rgba(248,113,113,0.05)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: '10px', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#e8eef8' }}>{rule.rule_name}</div>
                  <div style={{ color: '#6677aa', fontSize: '0.79rem', marginTop: '0.2rem' }}>{rule.explanation}</div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f87171' }}>{rule.impact > 0 ? `+${rule.impact}` : rule.impact}</div>
                  <div style={{ fontSize: '0.7rem', color: '#556688', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{rule.category}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Warnings ── */}
        {tab === 'warnings' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {warns.length === 0
              ? <div style={{ textAlign: 'center', color: '#4ade80', padding: '2rem', fontSize: '0.9rem' }}>✓ No validation warnings.</div>
              : warns.map((w, i) => (
                <div key={i} style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: '8px', padding: '0.75rem 1rem', color: '#fbbf24', fontSize: '0.85rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                  <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <span>{w}</span>
                </div>
              ))
            }
          </div>
        )}

        {/* ── Chat ── */}
        {tab === 'chat' && (
          <ChatPanel analysisId={analysisId} companyName={data.company_name} />
        )}

      </div>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────

const centerStyle: React.CSSProperties = {
  minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', background: '#0c1220', fontFamily: "'IBM Plex Sans', sans-serif",
};
const spinnerStyle: React.CSSProperties = {
  width: '38px', height: '38px', border: '3px solid rgba(79,142,247,0.15)',
  borderTop: '3px solid #4f8ef7', borderRadius: '50%', animation: 'spin 1s linear infinite',
};
function btnStyle(bg: string): React.CSSProperties {
  return { padding: '0.55rem 1.1rem', background: bg, border: 'none', borderRadius: '9px', color: '#e8eef8', fontWeight: 600, fontSize: '0.85rem', cursor: 'pointer' };
}

// ─────────────────────────────────────────────────────────────────────────────
// Export with Suspense (required for useSearchParams in Next.js 14)
// ─────────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0c1220', color: '#667799', fontFamily: "'IBM Plex Sans',sans-serif" }}>
        Loading...
      </div>
    }>
      <DashboardContent />
    </Suspense>
  );
}
