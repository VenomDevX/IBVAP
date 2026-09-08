import { useState, useEffect } from 'react';
import { apiFetch, getRiskEmoji } from '../../api/client';
import { useInterval } from '../../hooks/useInterval';
import type { ThreatsData } from '../../types';

export default function ThreatScorePanel() {
  const [threatsData, setThreatsData] = useState<ThreatsData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchThreats = async () => {
    try {
      const res = await apiFetch('/api/statistics/threats');
      setThreatsData(await res.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load threats:', err);
    }
  };

  useEffect(() => { fetchThreats(); }, []);
  useInterval(fetchThreats, 3000);

  if (loading) {
    return <div className="card loading"><i className="fas fa-spinner fa-spin" /> Loading Threat Scores...</div>;
  }

  const threats = threatsData?.top_threats || [];

  return (
    <div className="card threat-panel">
      <div className="card-header">
        <h3><i className="fas fa-shield-alt text-danger"></i> Live Threat Assessment</h3>
      </div>
      <div className="card-body">
        {threats.length === 0 ? (
          <div className="empty-state">
            <i className="fas fa-check-circle text-success" style={{ fontSize: '2rem', marginBottom: '1rem' }}></i>
            <p>No active threats detected.</p>
          </div>
        ) : (
          <div className="threat-list">
            {threats.map((threat) => (
              <div key={threat.track_id} className={`threat-item risk-${threat.risk_level}`} style={{ marginBottom: '1.5rem', padding: '1rem', borderRadius: '8px', backgroundColor: 'var(--surface)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.5rem' }}>{getRiskEmoji(threat.risk_level)}</span>
                    <strong style={{ textTransform: 'capitalize', fontSize: '1.1rem' }}>{threat.object_type}</strong>
                    <span className="badge" style={{ backgroundColor: 'var(--border)' }}>{threat.camera_id}</span>
                  </div>
                  
                  {/* Gauge */}
                  <div className="threat-gauge" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ 
                      width: '100px', height: '8px', borderRadius: '4px', backgroundColor: 'var(--border)', overflow: 'hidden',
                      position: 'relative'
                    }}>
                      <div style={{
                        position: 'absolute', top: 0, left: 0, height: '100%',
                        width: `${threat.risk_score}%`,
                        backgroundColor: threat.risk_score > 75 ? 'var(--danger)' : threat.risk_score > 50 ? 'var(--warning)' : 'var(--success)',
                        transition: 'width 0.5s ease-out'
                      }}></div>
                    </div>
                    <strong style={{ 
                      color: threat.risk_score > 75 ? 'var(--danger)' : threat.risk_score > 50 ? 'var(--warning)' : 'var(--success)'
                    }}>
                      {threat.risk_score}/100
                    </strong>
                  </div>
                </div>
                
                {/* Factors */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem' }}>
                  {threat.risk_factors.map((factor, idx) => (
                    <span key={idx} style={{ 
                      fontSize: '0.8rem', padding: '0.2rem 0.5rem', borderRadius: '4px',
                      backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)'
                    }}>
                      <i className="fas fa-exclamation-triangle" style={{ marginRight: '0.3rem', color: 'var(--warning)', fontSize: '0.7rem' }}></i>
                      {factor}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
