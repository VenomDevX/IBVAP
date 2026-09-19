'use client';

import dynamic from 'next/dynamic';
import { Loading } from '@/src/components/ui/States';

// Leaflet touches window at import time, so it only loads in the browser.
const CameraMap = dynamic(() => import('@/src/components/map/CameraMap'), {
  ssr: false,
  loading: () => <Loading label="Loading map…" />,
});

export default function MapPage() {
  return <CameraMap />;
}
