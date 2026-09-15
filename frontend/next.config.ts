import type { NextConfig } from 'next';

/**
 * Same deployment model as frontend/: a client-rendered SPA exported as static
 * files. In dev the browser calls the backend cross-origin via
 * NEXT_PUBLIC_API_BASE (backend CORS allows :3001).
 */
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  devIndicators: false,
  // Page-data workers default to one per core; on a machine that also runs the
  // GPU pipeline that exhausts memory and crashes the build.
  experimental: { cpus: 4 },
};

export default nextConfig;
