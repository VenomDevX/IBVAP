import type { NextConfig } from 'next';

/**
 * The app is a pure client-rendered SPA served as static files by nginx
 * (see Dockerfile / nginx.conf), which proxies /api, /ws, /snapshots and
 * /static to the FastAPI backend. In dev the browser talks to the backend
 * cross-origin via NEXT_PUBLIC_API_BASE (backend CORS already allows :3001).
 */
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  devIndicators: false,
};

export default nextConfig;
