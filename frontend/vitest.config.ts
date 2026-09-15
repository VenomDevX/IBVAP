import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    // tests/e2e holds Playwright specs, run with `npm run test:e2e`
    exclude: ['node_modules/**', 'tests/e2e/**'],
  },
});
