import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchConversation, resolveConversation } from '../api';

const STATE_LABELS = {
  booked: 'BOOKED',
  rescheduled: 'RESCHEDULED',
  cancelled: 'CANCELLED',
  escalated: 'ESCALATED',
  refused: 'REFUSED',
  abandoned: 'ABANDONED',
};

function formatArgs(args) {
  return Object.entries(args || {})
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ');
}

function formatResult(result) {
  if (result == null) return '';
  if (result.error) return `error: ${result.error}`;
  if (Array.isArray(result.slots)) return `${result.slots.length} slots: ${result.slots.join(', ')}`;
  if (Array.isArray(result.candidates)) return `${result.candidates.length} candidate(s): ${result.candidates.map((c) => `${c.name} (${c.id})`).join(', ')}`;
  if (result.id) return `-> ${result.id} on ${result.date} ${result.start}`;
  if ('success' in result) return `success=${result.success}`;
  if (result.status) return `status=${result.status}`;
  return JSON.stringify(result);
}

export default function ConversationDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    fetchConversation(id).then(setData).catch((e) => setError(e.message));
  };

  useEffect(() => {
    setData(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleResolve = async () => {
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
        <p style={{ color: '#ef4444' }}>{error}</p>
        <Link to="/">&larr; Back to Handoff Queue</Link>
      </div>
    );
  }

  if (!data) {
    return <div className="main-content">Loading…</div>;
  }

  const isEscalated = data.terminal_state === 'escalated';
  const transcript = data.transcript || [];

  return (
    <div className="main-content">
      <div className="page-header">
        <div>
          <h1 className="page-title">Conversation {data.conversation_id}</h1>
          <p className="page-subtitle">
            Sunrise Clinic, Dehradun — {data.today} {data.recorded_at ? `(recorded ${new Date(data.recorded_at).toLocaleString()})` : ''}
          </p>
        </div>
        <div className={`pill-badge ${isEscalated ? 'urgent' : ''}`}>
          {STATE_LABELS[data.terminal_state] || data.terminal_state}
          {data.escalation_reason ? ` — ${data.escalation_reason.toUpperCase()}` : ''}
        </div>
      </div>

      <div className="conversation-layout">
        <div className="panel">
          <div className="panel-header">Transcript and tool calls</div>
          <div className="transcript-body">
            {transcript.length === 0 && (
              <p style={{ color: '#64748b', fontSize: '14px' }}>No transcript recorded for this conversation.</p>
            )}
            {transcript.map((turn, i) => {
              if (turn.role === 'caller') {
                return (
                  <div className="chat-turn" key={i}>
                    <div className="chat-avatar">CALLER</div>
                    <div className="chat-bubble">{turn.text}</div>
                  </div>
                );
              }
              if (turn.role === 'tool') {
                return (
                  <div className="chat-turn" key={i}>
                    <div className="chat-avatar">TOOL</div>
                    <div className="chat-bubble tool">
                      {turn.name}({formatArgs(turn.arguments)})<br />
                      ↳ {formatResult(turn.result)}
                    </div>
                  </div>
                );
              }
              return (
                <div className="chat-turn" key={i}>
                  <div className="chat-avatar">AGENT</div>
                  <div className={`chat-bubble ${isEscalated && i === transcript.length - 1 ? 'system' : 'agent'}`}>
                    {turn.text}
                  </div>
                </div>
              );
            })}

            {data.terminal_state === 'abandoned' && (
              <div style={{ textAlign: 'center', marginTop: '16px' }}>
                <span style={{ backgroundColor: '#fee2e2', color: '#b91c1c', padding: '6px 16px', borderRadius: '4px', fontSize: '13px', fontWeight: 500 }}>
                  Booking flow abandoned. No appointment was created.
                </span>
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="panel">
            <div className="panel-header">Outcome</div>
            <div className="outcome-body">
              <div className="outcome-row">
                <span className="outcome-label">terminal_state</span>
                <span className="outcome-value">{data.terminal_state}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">escalation_reason</span>
                <span className="outcome-value">{data.escalation_reason ?? 'null'}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">patient_id</span>
                <span className="outcome-value">{data.patient_id ?? 'null'}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">appointment_id</span>
                <span className="outcome-value">{data.appointment_id ?? 'null'}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">tool_calls</span>
                <span className="outcome-value" style={{ fontFamily: 'inherit' }}>{data.tool_calls?.length ?? 0}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">turns</span>
                <span className="outcome-value" style={{ fontFamily: 'inherit' }}>{data.metrics?.turns ?? '—'}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">tokens</span>
                <span className="outcome-value" style={{ fontFamily: 'inherit' }}>{data.metrics?.tokens?.toLocaleString?.() ?? '—'}</span>
              </div>
              <div className="outcome-row">
                <span className="outcome-label">latency</span>
                <span className="outcome-value" style={{ fontFamily: 'inherit' }}>
                  {data.metrics?.latency_ms != null ? `${(data.metrics.latency_ms / 1000).toFixed(1)} s` : '—'}
                </span>
              </div>

              <div className="determinism-block">
                <div className="determinism-title">DETERMINISM</div>
                <div className="determinism-status">
                  Verified via <code>runner.py --repeat 3</code>, not re-checked live here.
                </div>
              </div>

              {isEscalated && (
                <div className="determinism-block">
                  <div className="determinism-title">RESOLUTION</div>
                  {data.resolved ? (
                    <div className="determinism-status">
                      Resolved <span className="status-badge">DONE</span>
                    </div>
                  ) : (
                    <button className="btn-resolve" onClick={handleResolve}>Resolve</button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
