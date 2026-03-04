'use client';

import { useState, useRef, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Send, Bot, User, BookOpen, AlertCircle, Loader2 } from 'lucide-react';

interface Source {
  title: string;
  category: string;
  relevance: number;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  rag_chunks_used?: number;
}

const SUGGESTED_QUESTIONS = [
  'Why was this company approved or rejected?',
  'What do the DSCR and ICR numbers mean for this borrower?',
  'Explain the GST compliance risk in simple terms.',
  'What conditions should we impose if approving this loan?',
  'How does this company compare to a typical approved borrower?',
  'What are the key red flags the bank should monitor?',
];

function ChatContent() {
  const params = useSearchParams();
  const analysisId = params.get('id') || '';
  const companyName = params.get('name') || 'This Company';

  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Hello! I'm the Intelli-Credit AI analyst assistant. I have full access to the credit analysis for **${companyName}** — including the Five Cs scores, extracted financials, triggered risk rules, and retrieved RBI/GST/MCA regulations.\n\nAsk me anything about this credit appraisal. I'll cite specific numbers from the analysis and relevant Indian banking regulations.`,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading || !analysisId) return;

    const userMsg: Message = { role: 'user', content: text.trim() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setError('');

    const history = messages
      .filter(m => m.role !== 'assistant' || messages.indexOf(m) > 0)
      .map(m => ({ role: m.role, content: m.content }));

    try {
      const { data } = await api.post(`/chat/${analysisId}`, {
        question: text.trim(),
        conversation_history: history,
      });

      const assistantMsg: Message = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources || [],
        rag_chunks_used: data.rag_chunks_used || 0,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Failed to get response. Check backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const categoryColor: Record<string, string> = {
    rbi_guidelines:     '#4f8ef7',
    gst_regulations:    '#fb923c',
    mca_regulations:    '#a78bfa',
    credit_norms:       '#34d399',
    governance:         '#f472b6',
    fraud_prevention:   '#f87171',
    sector_intelligence:'#fbbf24',
    historical_decisions:'#6ee7b7',
  };

  if (!analysisId) {
    return (
      <div style={centerStyle}>
        <AlertCircle size={40} style={{ color: '#f87171' }} />
        <p style={{ color: '#f87171', marginTop: '1rem' }}>No analysis ID provided.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0c1220', fontFamily: "'IBM Plex Sans', sans-serif", color: '#fff' }}>

      {/* Header */}
      <div style={{ background: 'rgba(26,39,68,0.95)', borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '0.875rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem', backdropFilter: 'blur(10px)' }}>
        <div style={{ background: 'linear-gradient(135deg, #4f8ef7, #2c5fd4)', width: '36px', height: '36px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Bot size={20} />
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>Intelli-Credit AI Analyst</div>
          <div style={{ fontSize: '0.78rem', color: '#8899cc' }}>RAG-powered · {companyName} · Cites RBI/GST/MCA regulations</div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
          <a href={`/dashboard?id=${analysisId}`} style={{ padding: '0.4rem 0.9rem', background: 'rgba(79,142,247,0.15)', border: '1px solid rgba(79,142,247,0.3)', borderRadius: '8px', color: '#7baeff', fontSize: '0.8rem', textDecoration: 'none', fontWeight: 600 }}>
            ← Dashboard
          </a>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        {/* Suggested Questions (show only initially) */}
        {messages.length === 1 && (
          <div style={{ background: 'rgba(79,142,247,0.06)', border: '1px solid rgba(79,142,247,0.15)', borderRadius: '14px', padding: '1rem 1.25rem' }}>
            <p style={{ color: '#8899cc', fontSize: '0.8rem', marginBottom: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Try asking</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {SUGGESTED_QUESTIONS.map(q => (
                <button key={q} onClick={() => sendMessage(q)} style={{ padding: '0.45rem 0.9rem', background: 'rgba(79,142,247,0.1)', border: '1px solid rgba(79,142,247,0.25)', borderRadius: '20px', color: '#7baeff', fontSize: '0.82rem', cursor: 'pointer', transition: 'all 0.15s' }}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.75rem', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', alignItems: 'flex-start' }}>
            {/* Avatar */}
            <div style={{ width: '32px', height: '32px', borderRadius: '8px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: msg.role === 'user' ? 'rgba(79,142,247,0.2)' : 'linear-gradient(135deg, #4f8ef7, #2c5fd4)' }}>
              {msg.role === 'user' ? <User size={16} style={{ color: '#7baeff' }} /> : <Bot size={16} />}
            </div>

            <div style={{ maxWidth: '75%', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {/* Bubble */}
              <div style={{ background: msg.role === 'user' ? 'rgba(79,142,247,0.15)' : 'rgba(255,255,255,0.05)', border: `1px solid ${msg.role === 'user' ? 'rgba(79,142,247,0.25)' : 'rgba(255,255,255,0.08)'}`, borderRadius: msg.role === 'user' ? '14px 4px 14px 14px' : '4px 14px 14px 14px', padding: '0.875rem 1.1rem', fontSize: '0.92rem', lineHeight: '1.6', color: '#e8ecf4', whiteSpace: 'pre-wrap' }}>
                {msg.content}
              </div>

              {/* RAG Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <BookOpen size={12} style={{ color: '#8899cc', flexShrink: 0 }} />
                  <span style={{ color: '#8899cc', fontSize: '0.72rem' }}>Sources ({msg.rag_chunks_used} chunks):</span>
                  {msg.sources.map((s, si) => (
                    <span key={si} style={{ padding: '0.2rem 0.55rem', background: `${categoryColor[s.category] || '#8899cc'}18`, border: `1px solid ${categoryColor[s.category] || '#8899cc'}40`, borderRadius: '10px', fontSize: '0.72rem', color: categoryColor[s.category] || '#8899cc' }}>
                      {s.title} ({(s.relevance * 100).toFixed(0)}%)
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '8px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #4f8ef7, #2c5fd4)' }}>
              <Bot size={16} />
            </div>
            <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '4px 14px 14px 14px', padding: '0.875rem 1.1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#8899cc', fontSize: '0.88rem' }}>
              <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              Retrieving regulations and analysing...
            </div>
          </div>
        )}

        {error && (
          <div style={{ background: 'rgba(200,57,43,0.1)', border: '1px solid rgba(200,57,43,0.3)', borderRadius: '10px', padding: '0.75rem 1rem', color: '#ff7c6e', fontSize: '0.88rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <AlertCircle size={14} />{error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ background: 'rgba(26,39,68,0.95)', borderTop: '1px solid rgba(255,255,255,0.08)', padding: '1rem 1.5rem', backdropFilter: 'blur(10px)' }}>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', maxWidth: '900px', margin: '0 auto' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this credit analysis... (Enter to send, Shift+Enter for new line)"
            rows={1}
            style={{ flex: 1, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '10px', padding: '0.75rem 1rem', color: '#fff', fontSize: '0.92rem', resize: 'none', outline: 'none', fontFamily: 'inherit', maxHeight: '120px', overflow: 'auto' }}
            onInput={e => {
              const el = e.target as HTMLTextAreaElement;
              el.style.height = 'auto';
              el.style.height = Math.min(el.scrollHeight, 120) + 'px';
            }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={loading || !input.trim()}
            style={{ padding: '0.75rem', background: loading || !input.trim() ? 'rgba(79,142,247,0.3)' : 'linear-gradient(135deg, #4f8ef7, #2c5fd4)', border: 'none', borderRadius: '10px', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s', flexShrink: 0 }}
          >
            <Send size={18} style={{ color: '#fff' }} />
          </button>
        </div>
        <p style={{ textAlign: 'center', color: '#556080', fontSize: '0.72rem', marginTop: '0.5rem' }}>
          Powered by Claude + ChromaDB RAG · Retrieves RBI, GST, MCA regulations in real-time
        </p>
      </div>
    </div>
  );
}

const centerStyle: React.CSSProperties = {
  minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', background: '#0c1220', color: '#fff', fontFamily: "'IBM Plex Sans', sans-serif"
};

export default function ChatPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0c1220', color: '#8899cc' }}>Loading...</div>}>
      <ChatContent />
    </Suspense>
  );
}
