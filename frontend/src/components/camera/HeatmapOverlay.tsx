import { useState } from 'react';
import { useInterval } from '../../hooks/useInterval';
import { useAuth } from '../../context/AuthContext';
import { mediaSrc } from '../../api/client';

interface HeatmapOverlayProps {
  cameraId: string;
  isVisible: boolean;
  windowMinutes?: number;
}

export default function HeatmapOverlay({ cameraId, isVisible, windowMinutes = 5 }: HeatmapOverlayProps) {
  const [timestamp, setTimestamp] = useState(Date.now());
  const { session } = useAuth();

  // Refresh heatmap every 5 seconds when visible
  useInterval(() => {
    if (isVisible) {
      setTimestamp(Date.now());
    }
  }, 5000);

  if (!isVisible) return null;

  const windowSeconds = windowMinutes * 60;
  
  const token = session?.access_token;

  return (
    <div className="heatmap-container" style={{
      position: 'absolute',
      top: 0,
      left: 0,
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: 10,
      opacity: 0.7,
      mixBlendMode: 'screen'
    }}>
      <img 
        src={mediaSrc(`/api/cameras/${cameraId}/heatmap?window=${windowSeconds}&t=${timestamp}`, token)}
        alt="Heatmap"
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain'
        }}
      />
    </div>
  );
}
