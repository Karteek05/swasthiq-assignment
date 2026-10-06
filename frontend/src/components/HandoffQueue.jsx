import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchQueue, resolveConversation } from '../api';

const REASON_LABELS = {
  clinical_urgent: 'CLINICAL',
  medical_advice: 'MEDICAL ADVICE',
  not_authorised: 'NOT AUTHORISED',
  ambiguous_patient: 'AMBIGUOUS PATIENT',
  out_of_scope: 'OUT OF SCOPE',
};

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function HandoffQueue() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    fetchQueue().then(setData).catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  const handleResolve = async (e, id) => {
    e.stopPropagation();
    try {
      await resolveConversation(id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  if (error) {
    return (
      <div className="main-content">
        <p style={{ color: '#ef4444' }}>
          Could not reach the backend ({error}). Is it running at {import.meta.env.VITE_API_URL || 'http://localhost:8000'}?
        </p>
      </div>
    );
  }

  if (!data) {
    return <div className="main-content">Loading…</div>;
  }

  const { counters, conversations } = data;
  const openHandoffs = conversations.filter((c) => c.terminal_state === 'escalated' && !c.resolved);

  return (
    <div className="main-content">
      <div className="page-header">
        <div>
          <h1 className="page-title">Handoff Queue</h1>
          <p className="page-subtitle">Sunrise Clinic, Dehradun — conversations the agent escalated</p>
        </div>
        <div className="pill-badge">{openHandoffs.length} OPEN</div>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">CONVERSATIONS</div>
          <div className="metric-value">{counters.conversations_today}</div>
          <div className="metric-sub">today</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">COMPLETED BY AGENT</div>
          <div className="metric-value">{counters.completed_by_agent}</div>
          <div className="metric-sub">{counters.completed_by_agent_pct}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">ESCALATED</div>
          <div className="metric-value">{counters.escalated}</div>
          <div className="metric-sub alert">{counters.escalated_open} still open</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">URGENT</div>
          <div className="metric-value">{counters.urgent_open}</div>
          <div className="metric-sub danger">clinical, unresolved</div>
        </div>
      </div>

      <div className="table-container">
        <div className="table-header-title">Open handoffs</div>
        {openHandoffs.length === 0 ? (
          <div style={{ padding: '24px', color: '#64748b', fontSize: '14px' }}>
            Nothing waiting on a human right now.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>CONVERSATION</th>
                <th>CALLER SAID</th>
                <th>REASON</th>
                <th>TIME</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {openHandoffs.map((h) => (
                <tr key={h.conversation_id} onClick={() => navigate(`/conversation/${h.conversation_id}`)} style={{ cursor: 'pointer' }}>
                  <td style={{ color: '#64748b' }}>{h.conversation_id}</td>
                  <td style={{ fontWeight: 500 }}>&ldquo;{h.caller_said}&rdquo;</td>
                  <td>
                    <span className={`reason-tag ${h.escalation_reason === 'clinical_urgent' ? 'clinical' : ''}`}>
                      {REASON_LABELS[h.escalation_reason] || h.escalation_reason}
                    </span>
                  </td>
                  <td style={{ color: '#64748b' }}>{formatTime(h.recorded_at)}</td>
                  <td>
                    <button className="btn-resolve" onClick={(e) => handleResolve(e, h.conversation_id)}>
                      Resolve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
