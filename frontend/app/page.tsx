'use client';

import { useState, useRef, DragEvent } from 'react';
import { useRouter } from 'next/navigation';
import { analyzeDocument } from '@/lib/api';
import { Upload, FileText, Zap, Shield, BarChart3, AlertCircle } from 'lucide-react';

export default function HomePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [companyName, setCompanyName] = useState('');
  const [loanAmount, setLoanAmount] = useState('');
  const [primaryInsights, setPrimaryInsights] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.toLowerCase().endsWith('.pdf')) {
      setFile(dropped);
      setError('');
    } else {
      setError('Only PDF files are supported.');
    }
  };

  const handleSubmit = async () => {
    if (!file) return setError('Please upload a PDF document.');
    if (!companyName.trim()) return setError('Please enter the company name.');
    setLoading(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('company_name', companyName);
      if (loanAmount) formData.append('loan_amount_requested', loanAmount);
      if (primaryInsights) formData.append('primary_insights', primaryInsights);
      const result = await analyzeDocument(formData);
      router.push(`/dashboard?id=${result.analysis_id}`);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Analysis failed. Please check the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #0f1628 0%, #1a2744 50%, #0f2040 100%)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem', fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {/* Logo */}
      <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
        <h1 style={{ fontSize: '2.8rem', fontWeight: 800, color: '#fff', letterSpacing: '-1px', margin: 0 }}>
          Intelli<span style={{ color: '#4f8ef7' }}>Credit</span>
        </h1>
        <p style={{ color: '#8899cc', marginTop: '0.5rem', fontSize: '1.05rem' }}>
          AI-Powered Corporate Credit Decisioning Engine
        </p>
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '1rem', flexWrap: 'wrap' }}>
          {['Deterministic Scoring', 'Anti-Hallucination', 'CAM Generation', 'Indian Regulatory'].map(tag => (
            <span key={tag} style={{ background: 'rgba(79,142,247,0.15)', color: '#7baeff', padding: '0.25rem 0.75rem', borderRadius: '20px', fontSize: '0.78rem', border: '1px solid rgba(79,142,247,0.3)' }}>{tag}</span>
          ))}
        </div>
      </div>

      {/* Card */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '20px', padding: '2.5rem', width: '100%', maxWidth: '600px', backdropFilter: 'blur(10px)' }}>
        {/* Drop Zone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          style={{ border: `2px dashed ${dragging ? '#4f8ef7' : file ? '#1a7a4a' : 'rgba(255,255,255,0.2)'}`, borderRadius: '12px', padding: '2rem', textAlign: 'center', cursor: 'pointer', transition: 'all 0.2s', background: dragging ? 'rgba(79,142,247,0.05)' : 'transparent', marginBottom: '1.5rem' }}
        >
          <input ref={fileInputRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setError(''); } }} />
          {file ? (
            <><FileText size={36} style={{ color: '#1a7a4a', marginBottom: '0.5rem' }} /><p style={{ color: '#4ade80', fontWeight: 600, margin: 0 }}>{file.name}</p><p style={{ color: '#8899cc', fontSize: '0.85rem', margin: '0.25rem 0 0' }}>{(file.size / 1024).toFixed(0)} KB — click to change</p></>
          ) : (
            <><Upload size={36} style={{ color: '#4f8ef7', marginBottom: '0.5rem' }} /><p style={{ color: '#fff', fontWeight: 600, margin: 0 }}>Drop PDF here or click to upload</p><p style={{ color: '#8899cc', fontSize: '0.85rem', margin: '0.25rem 0 0' }}>Max 20 MB · Text-based PDF only</p></>
          )}
        </div>

        {/* Fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ color: '#aabbdd', fontSize: '0.85rem', display: 'block', marginBottom: '0.4rem' }}>Company Name *</label>
            <input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="e.g. ABC Industries Pvt Ltd" style={{ width: '100%', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', color: '#fff', fontSize: '0.95rem', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div>
            <label style={{ color: '#aabbdd', fontSize: '0.85rem', display: 'block', marginBottom: '0.4rem' }}>Loan Amount Requested (₹)</label>
            <input type="number" value={loanAmount} onChange={e => setLoanAmount(e.target.value)} placeholder="e.g. 50000000 (5 Crore)" style={{ width: '100%', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', color: '#fff', fontSize: '0.95rem', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div>
            <label style={{ color: '#aabbdd', fontSize: '0.85rem', display: 'block', marginBottom: '0.4rem' }}>Primary Management Insights <span style={{ color: '#8899cc' }}>(optional)</span></label>
            <textarea value={primaryInsights} onChange={e => setPrimaryInsights(e.target.value)} rows={3} placeholder="e.g. Promoter has 20 years experience, strong succession plan, sector facing headwinds due to..." style={{ width: '100%', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', color: '#fff', fontSize: '0.9rem', outline: 'none', resize: 'vertical', boxSizing: 'border-box' }} />
          </div>
        </div>

        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(200,57,43,0.15)', border: '1px solid rgba(200,57,43,0.4)', borderRadius: '8px', padding: '0.75rem 1rem', marginTop: '1rem', color: '#ff7c6e' }}>
            <AlertCircle size={16} /><span style={{ fontSize: '0.9rem' }}>{error}</span>
          </div>
        )}

        <button onClick={handleSubmit} disabled={loading} style={{ width: '100%', marginTop: '1.5rem', padding: '1rem', background: loading ? 'rgba(79,142,247,0.4)' : 'linear-gradient(135deg, #4f8ef7, #2c5fd4)', border: 'none', borderRadius: '10px', color: '#fff', fontSize: '1rem', fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer', transition: 'all 0.2s' }}>
          {loading ? '⏳ Analysing Document...' : '🚀 Run Credit Analysis'}
        </button>
      </div>

      {/* Feature grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '2rem', maxWidth: '600px', width: '100%' }}>
        {[
          { icon: <Zap size={20} />, title: 'Five Cs Scoring', desc: 'Deterministic rule-based engine' },
          { icon: <Shield size={20} />, title: 'Anti-Hallucination', desc: 'Evidence required for every field' },
          { icon: <BarChart3 size={20} />, title: 'CAM Generation', desc: 'ReportLab PDF with full audit trail' },
        ].map(f => (
          <div key={f.title} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '1rem', textAlign: 'center' }}>
            <div style={{ color: '#4f8ef7', marginBottom: '0.4rem' }}>{f.icon}</div>
            <div style={{ color: '#fff', fontWeight: 600, fontSize: '0.85rem' }}>{f.title}</div>
            <div style={{ color: '#8899cc', fontSize: '0.75rem', marginTop: '0.25rem' }}>{f.desc}</div>
          </div>
        ))}
      </div>
    </main>
  );
}
