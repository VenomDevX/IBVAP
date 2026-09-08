import { useAuth } from '../context/AuthContext';
import { mediaSrc } from '../api/client';
import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import type { Camera, ThreatsData } from '../types';

export default function MultiView() {
  const { session } = useAuth();
  const token = session?.access_token;
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [gridSize, setGridSize] = useState<4 | 9 | 16>(4); // 2x2, 3x3, 4x4
  const [loading, setLoading] = useState(true);

  // Load cameras and threat data
  const fetchData = async () => {
    try {
      const [camRes, threatRes] = await Promise.all([
        apiFetch('/api/cameras'),
        apiFetch('/api/statistics/threats')
      ]);
      setCameras(await camRes.json());
      setThreats(await threatRes.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load multiview data:', err);
    }
  };

  useEffect(() => { fetchData(); }, []);
  useInterval(fetchData, 5000);

  if (loading) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Multi-Camera View...</div>;
  }

  // Get up to `gridSize` cameras
  const activeCameras = cameras.slice(0, gridSize);

  return (
    <div className="multiview-page">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2><i className="fas fa-th-large"></i> Multi-Camera View</h2>
        <div className="grid-controls" style={{ display: 'flex', gap: '0.5rem' }}>
          <button 
            className={`btn btn-sm ${gridSize === 4 ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setGridSize(4)}
          >
            2×2
          </button>
          <button 
            className={`btn btn-sm ${gridSize === 9 ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setGridSize(9)}
          >
            3×3
          </button>
          <button 
            className={`btn btn-sm ${gridSize === 16 ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setGridSize(16)}
          >
            4×4
          </button>
        </div>
      </div>

      <div 
        className="camera-grid-multiview" 
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${Math.sqrt(gridSize)}, 1fr)`,
          gap: '10px',
          height: 'calc(100vh - 150px)'
        }}
      >
        {Array.from({ length: gridSize }).map((_, idx) => {
          const cam = activeCameras[idx];
          const camThreatCount = cam && threats?.camera_distribution ? threats.camera_distribution[cam.camera_id] || 0 : 0;

          return (
            <div 
              key={idx} 
              className="multiview-cell"
              style={{
                backgroundColor: '#000',
                borderRadius: '8px',
                overflow: 'hidden',
                position: 'relative',
                border: camThreatCount > 0 ? '2px solid var(--danger)' : '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              {cam ? (
                <>
                  <img
                    src={mediaSrc(`/api/stream/${cam.camera_id}`, token)}
                    alt={cam.name}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  
                  {/* Overlay Meta */}
                  <div style={{
                    position: 'absolute',
                    top: 0, left: 0, width: '100%',
                    padding: '5px 10px',
                    background: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start'
                  }}>
                    <div style={{ color: '#fff', textShadow: '1px 1px 2px #000' }}>
                      <strong style={{ display: 'block', fontSize: '0.9rem' }}>{cam.name}</strong>
                      <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>{cam.camera_id}</span>
                    </div>
                    {camThreatCount > 0 && (
                      <div style={{ 
                        backgroundColor: 'var(--danger)', color: '#fff', 
                        padding: '2px 6px', borderRadius: '4px', fontSize: '0.8rem',
                        fontWeight: 'bold', animation: 'pulse 2s infinite'
                      }}>
                        <i className="fas fa-exclamation-triangle" style={{ marginRight: '4px' }}></i>
                        {camThreatCount} Threats
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <i className="fas fa-video-slash" style={{ fontSize: '2rem', marginBottom: '0.5rem' }}></i>
                  <span>No Camera</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
