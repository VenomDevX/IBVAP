import { useEffect, useState } from 'react';
import { apiFetch, getRiskEmoji } from '../../api/client';
import { useInterval } from '../../hooks/useInterval';
import Card from '../ui/Card';
import type { Threat, ThreatsData } from '../../types';

function sevClass(score: number): string {
  if (score > 75) return 'sev-high';
  if (score > 50) return 'sev-medium';
  return 'sev-low';
}

function ThreatRow({ threat }: { threat: Threat }) {
  const sev = sevClass(threat.risk_score);
  return (
    <div className={`threat-item risk-${threat.risk_level}`}>
      <div className="threat-head">
        <div className="threat-id">
          <span className="threat-emoji">{getRiskEmoji(threat.risk_level)}</span>
          <strong className="threat-obj">{threat.object_type}</strong>
          <span className="threat-cam">{threat.camera_id}</span>
        </div>
        <div className="threat-gauge">
          <div className="threat-gauge-track">
            <div className={`threat-gauge-fill ${sev}`} style={{ width: `${threat.risk_score}%` }} />
          </div>
          <span className={`threat-score ${sev}`}>{threat.risk_score}/100</span>
        </div>
      </div>
      {threat.risk_factors.length > 0 && (
        <div className="threat-factors">
          {threat.risk_factors.map((factor, i) => (
            <span key={i} className="threat-factor">
              <i className="fas fa-exclamation-triangle" />{factor}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ThreatScorePanel() {
  const [threats, setThreats] = useState<Threat[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchThreats = async () => {
    try {
      const res = await apiFetch('/api/statistics/threats');
      const data: ThreatsData = await res.json();
      setThreats(data?.top_threats ?? []);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load threats:', err);
    }
  };

  useEffect(() => { fetchThreats(); }, []);
  useInterval(fetchThreats, 3000);

  if (loading) {
    return (
      <div className="card loading">
        <i className="fas fa-spinner fa-spin" /> Loading Threat Scores...
      </div>
    );
  }

  return (
    <Card title="Live Threat Assessment" icon="fas fa-shield-alt" className="threat-panel">
      {threats.length === 0 ? (
        <div className="empty-state">
          <i className="fas fa-check-circle" />
          <p>No active threats detected.</p>
        </div>
      ) : (
        <div className="threat-list">
          {threats.map(t => <ThreatRow key={t.track_id} threat={t} />)}
        </div>
      )}
    </Card>
  );
}
