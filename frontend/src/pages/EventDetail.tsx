import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiFetch, formatEventType, formatTime, getRiskEmoji } from '../api/client';
import Card from '../components/ui/Card';
import type { Event } from '../types';

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  const [event, setEvent] = useState<Event | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!eventId) return;
    apiFetch(`/api/events/${eventId}`)
      .then(r => r.json())
      .then(setEvent)
      .catch(() => setError(true));
  }, [eventId]);

  if (error) {
    return <div className="empty-state"><i className="fas fa-exclamation-circle" /><p>Event not found</p></div>;
  }

  if (!event) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading event...</div>;
  }

  return (
    <div className="event-detail">
      <div className="detail-header">
        <div className={`risk-indicator ${event.risk_level}`}>
          <span className="risk-emoji">{getRiskEmoji(event.risk_level)}</span>
          <span className="risk-text">{event.risk_level.toUpperCase()}</span>
          <span className="risk-score">{event.risk_score?.toFixed(0) || 0}/100</span>
        </div>
        <h2>{formatEventType(event.event_type)}</h2>
        <p className="event-meta">
          <span><i className="fas fa-video" /> {event.camera_id}</span>
          <span><i className="fas fa-clock" /> {formatTime(event.timestamp)}</span>
          <span><i className="fas fa-user" /> {event.object_type} (Track {event.track_id})</span>
        </p>
      </div>

      {event.temporal_context?.semantic_description && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 15, marginBottom: 20 }}>
          <h3 style={{ marginTop: 0, color: 'var(--accent-primary)' }}><i className="fas fa-align-left" /> AI Description</h3>
          <p style={{ marginBottom: 0, fontSize: '1.1em', lineHeight: 1.5 }}>{event.temporal_context.semantic_description}</p>
        </div>
      )}

      <div className="detail-grid">
        <Card title="Contributing Factors" icon="fas fa-list">
          <ul className="factor-list">
            {(event.contributing_factors || []).map((f, i) => (
              <li key={i}><i className="fas fa-check-circle" /> {f}</li>
            ))}
          </ul>
        </Card>

        <Card title="Spatial Context" icon="fas fa-map-pin">
          <div className="context-info">
            <p><strong>In Restricted Zone:</strong> {event.spatial_context?.in_restricted ? 'Yes' : 'No'}</p>
            <p><strong>Fence Crossed:</strong> {event.spatial_context?.fence_crossed ? 'Yes' : 'No'}</p>
            <p><strong>Zones:</strong> {(event.spatial_context?.zones || []).join(', ') || 'None'}</p>
          </div>
        </Card>

        <Card title="Temporal Context" icon="fas fa-clock">
          <div className="context-info">
            <p><strong>Night Time:</strong> {event.temporal_context?.is_night ? 'Yes' : 'No'}</p>
            <p><strong>Loitering:</strong> {event.temporal_context?.is_loitering ? 'Yes' : 'No'}</p>
            <p><strong>Duration:</strong> {event.duration?.toFixed(1) || 0}s</p>
          </div>
        </Card>

        {event.evidence_path && (
          <Card title="Evidence" icon="fas fa-image" className="evidence-card">
            <img
              src={`/snapshots/${event.evidence_path.replace(/\\\\/g, '/').split('/').pop()}`}
              alt="Evidence"
              className="evidence-img"
            />
            {event.evidence_hash && (
              <div style={{ marginTop: '10px', fontSize: '0.85em', color: '#666', wordBreak: 'break-all' }}>
                <strong>SHA-256 Hash:</strong> {event.evidence_hash}
              </div>
            )}
          </Card>
        )}
      </div>

      <div className="detail-actions">
        <Link to="/events" className="btn"><i className="fas fa-arrow-left" /> Back to Events</Link>
      </div>
    </div>
  );
}
