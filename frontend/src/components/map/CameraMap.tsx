'use client';

import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { apiFetch, riskMeta } from '../../api/client';
import { useInterval } from '../../hooks/useInterval';
import Icon from '../ui/Icon';
import { Loading } from '../ui/States';
import type { Camera, ThreatsData } from '../../types';

function pinIcon(color: string) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="38" viewBox="0 0 26 38">` +
    `<path d="M13 0C5.8 0 0 5.8 0 13c0 9.7 13 25 13 25s13-15.3 13-25C26 5.8 20.2 0 13 0z" fill="${color}"/>` +
    `<circle cx="13" cy="13" r="5" fill="#fff"/></svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [26, 38],
    iconAnchor: [13, 38],
    popupAnchor: [0, -34],
  });
}

const SECURE = pinIcon('#16a34a');
const ALERT = pinIcon('#dc2626');

export default function CameraMap() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [camRes, threatRes] = await Promise.all([
        apiFetch('/api/cameras'),
        apiFetch('/api/statistics/threats'),
      ]);
      setCameras(await camRes.json());
      setThreats(await threatRes.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load map data:', err);
    }
  };

  useEffect(() => { load(); }, []);
  useInterval(load, 5000);

  if (loading) return <Loading label="Loading map…" />;

  const located = cameras.filter(c => c.latitude != null && c.longitude != null);
  const centerLat = located.length
    ? located.reduce((s, c) => s + Number(c.latitude), 0) / located.length
    : 28.6139;
  const centerLng = located.length
    ? located.reduce((s, c) => s + Number(c.longitude), 0) / located.length
    : 77.209;

  return (
    <div className="overflow-hidden rounded-[3px] border border-default" style={{ height: 'calc(100vh - 7rem)' }}>
      <MapContainer center={[centerLat, centerLng]} zoom={13} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {located.map(cam => {
          const camThreats = threats?.top_threats?.filter(t => t.camera_id === cam.camera_id) ?? [];
          const count = threats?.camera_distribution?.[cam.camera_id] ?? 0;
          return (
            <Marker
              key={cam.camera_id}
              position={[Number(cam.latitude), Number(cam.longitude)]}
              icon={count > 0 ? ALERT : SECURE}
            >
              <Popup>
                <div className="min-w-52 font-sans">
                  <h3 className="m-0 text-sm font-semibold">{cam.name}</h3>
                  {cam.location && <p className="mb-2 mt-0.5 text-xs text-fg-subtle">{cam.location}</p>}
                  <p className="mb-2 flex items-center gap-1.5 text-xs">
                    <span
                      className="inline-block size-2 rounded-full"
                      style={{ background: cam.status === 'online' ? '#16a34a' : '#dc2626' }}
                    />
                    <span className="capitalize">{cam.status}</span>
                  </p>
                  {count > 0 ? (
                    <div className="text-xs">
                      <strong style={{ color: '#dc2626' }}>{count} active {count === 1 ? 'threat' : 'threats'}</strong>
                      <ul className="mb-0 mt-1 list-none space-y-1 p-0">
                        {camThreats.map((t, i) => (
                          <li key={i} className="flex items-center gap-1.5">
                            <span className="inline-block size-1.5 rounded-full" style={{ background: riskMeta(t.risk_level).color }} />
                            {t.object_type} · {t.risk_score.toFixed(0)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="m-0 flex items-center gap-1.5 text-xs" style={{ color: '#16a34a' }}>
                      <Icon name="circle-check" /> Secure
                    </p>
                  )}
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}
