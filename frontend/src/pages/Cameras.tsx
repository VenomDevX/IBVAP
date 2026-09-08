import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import type { Camera } from '../types';

export default function Cameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeHeatmaps, setActiveHeatmaps] = useState<Record<string, boolean>>({});

  const loadCameras = async () => {
    try {
      const res = await apiFetch('/api/cameras');
      setCameras(await res.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load cameras:', err);
    }
  };

  useEffect(() => { loadCameras(); }, []);
  useInterval(loadCameras, 10000);

  const toggleHeatmap = (cameraId: string) => {
    setActiveHeatmaps(prev => ({ ...prev, [cameraId]: !prev[cameraId] }));
  };

  if (loading) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading cameras...</div>;
  }

  if (cameras.length === 0) {
    return <div className="empty-state"><i className="fas fa-video-slash" /><p>No cameras configured</p></div>;
  }

  return (
    <div className="camera-grid">
      {cameras.map(c => (
        <div className="camera-card-item" key={c.camera_id} style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="camera-preview" style={{ position: 'relative' }}>
            <img
              src={`/api/stream/${c.camera_id}/snapshot`}
              alt={c.name}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
              onError={(e) => {
                const img = e.target as HTMLImageElement;
                img.style.display = 'none';
                const offline = img.parentElement?.querySelector('.camera-offline') as HTMLElement;
                if (offline) offline.style.display = 'flex';
              }}
            />
            {activeHeatmaps[c.camera_id] && (
              <img
                src={`/api/cameras/${c.camera_id}/heatmap`}
                alt={`${c.name} Heatmap`}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0.8, pointerEvents: 'none' }}
              />
            )}
            <div className="camera-offline" style={{ display: 'none', position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
              <i className="fas fa-video-slash" /><p>Offline</p>
            </div>
          </div>
          <div className="camera-info-bar">
            <div>
              <h4>{c.name}</h4>
              <span className="camera-id">{c.camera_id}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '5px' }}>
              <div className="camera-meta">
                <span className={`status-dot ${c.status === 'online' ? 'online' : 'offline'}`} />
                <span>{c.status}</span>
                {c.fps && <span className="fps-badge">{c.fps} FPS</span>}
              </div>
              <button 
                onClick={() => toggleHeatmap(c.camera_id)}
                className={`btn btn-xs ${activeHeatmaps[c.camera_id] ? 'btn-primary' : 'btn-outline'}`}
              >
                <i className="fas fa-fire"></i> {activeHeatmaps[c.camera_id] ? 'Hide Heatmap' : 'Show Heatmap'}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

