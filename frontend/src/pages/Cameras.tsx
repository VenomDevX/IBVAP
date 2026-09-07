import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import type { Camera } from '../types';

export default function Cameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);

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

  if (loading) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading cameras...</div>;
  }

  if (cameras.length === 0) {
    return <div className="empty-state"><i className="fas fa-video-slash" /><p>No cameras configured</p></div>;
  }

  return (
    <div className="camera-grid">
      {cameras.map(c => (
        <div className="camera-card-item" key={c.camera_id}>
          <div className="camera-preview">
            <img
              src={`/api/stream/${c.camera_id}/snapshot`}
              alt={c.name}
              onError={(e) => {
                const img = e.target as HTMLImageElement;
                img.style.display = 'none';
                const offline = img.nextElementSibling as HTMLElement;
                if (offline) offline.style.display = 'flex';
              }}
            />
            <div className="camera-offline" style={{ display: 'none' }}>
              <i className="fas fa-video-slash" /><p>Offline</p>
            </div>
          </div>
          <div className="camera-info-bar">
            <div>
              <h4>{c.name}</h4>
              <span className="camera-id">{c.camera_id}</span>
            </div>
            <div className="camera-meta">
              <span className={`status-dot ${c.status === 'online' ? 'online' : 'offline'}`} />
              <span>{c.status}</span>
              {c.fps && <span className="fps-badge">{c.fps} FPS</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
