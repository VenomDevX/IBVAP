import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3001,
    proxy: {
      '/api': 'http://localhost:8001',
      '/ws': { target: 'ws://localhost:8001', ws: true },
      '/snapshots': 'http://localhost:8001',
      '/static': 'http://localhost:8001',
    },
  },
  build: {
    outDir: 'dist',
  },
});
