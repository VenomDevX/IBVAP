import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { apiFetch, getRiskEmoji } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import type { Camera, ThreatsData } from '../types';

// Fix Leaflet's default icon path issues in React
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Custom Icons for threat status
const normalIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const dangerIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

export default function MapView() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [loading, setLoading] = useState(true);

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
      console.error('Failed to load map data:', err);
    }
  };

  useEffect(() => { fetchData(); }, []);
  useInterval(fetchData, 5000);

  if (loading) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Map View...</div>;
  }

  // Calculate map center (default to New Delhi if no cameras or coordinates)
  let centerLat = 28.6139;
  let centerLng = 77.2090;
  
  const validCameras = cameras.filter(c => c.latitude !== undefined && c.latitude !== null && c.longitude !== undefined && c.longitude !== null);
  if (validCameras.length > 0) {
    centerLat = validCameras.reduce((sum, c) => sum + (Number(c.latitude) || 0), 0) / validCameras.length;
    centerLng = validCameras.reduce((sum, c) => sum + (Number(c.longitude) || 0), 0) / validCameras.length;
  }

  return (
    <div className="map-page" style={{ height: 'calc(100vh - 112px)' }}>
      <div style={{ height: '100%', borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
        <MapContainer center={[centerLat, centerLng]} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {cameras.map(cam => {
            if (!cam.latitude || !cam.longitude) return null;
            
            const threatCount = threats?.camera_distribution[cam.camera_id] || 0;
            const camThreats = threats?.top_threats.filter(t => t.camera_id === cam.camera_id) || [];
            
            return (
              <Marker 
                key={cam.camera_id} 
                position={[cam.latitude, cam.longitude]}
                icon={threatCount > 0 ? dangerIcon : normalIcon}
              >
                <Popup>
                  <div style={{ minWidth: '200px' }}>
                    <h3 style={{ margin: '0 0 5px 0' }}>{cam.name}</h3>
                    <p style={{ margin: '0 0 10px 0', fontSize: '0.9em', color: '#666' }}>{cam.location}</p>
                    
                    <div style={{ marginBottom: '10px' }}>
                      <strong>Status: </strong> 
                      <span className={`status-dot ${cam.status === 'online' ? 'online' : 'offline'}`}></span>
                      {cam.status}
                    </div>

                    {threatCount > 0 ? (
                      <div>
                        <strong style={{ color: 'red' }}>{threatCount} Active Threats</strong>
                        <ul style={{ paddingLeft: '20px', margin: '5px 0' }}>
                          {camThreats.map((t, idx) => (
                            <li key={idx} style={{ fontSize: '0.9em' }}>
                              {getRiskEmoji(t.risk_level)} {t.object_type} (Score: {t.risk_score.toFixed(0)})
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div style={{ color: 'green', fontWeight: 'bold' }}>
                        <i className="fas fa-check-circle"></i> Secure
                      </div>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
