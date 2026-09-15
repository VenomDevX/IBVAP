# IBVAP frontend

Operator console for the Intelligent Border Video Analytics Platform: a client-rendered
Next.js 16 app exported as static files, styled with Tailwind v4.

## Run

```bash
npm install
npm run dev        # http://localhost:3001, calls the API at NEXT_PUBLIC_API_BASE (127.0.0.1:8002)
npm run build      # static export to out/
npm start          # serves out/ on :3001 and proxies /api, /ws, /snapshots to the backend
```

`.env` needs `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. In production the
API base is empty and nginx (`nginx.conf`, `Dockerfile`) serves the export and proxies the API.

## Checks

```bash
npm run typecheck && npm run lint && npm test
npm run test:e2e   # Playwright against a running app and backend (seeded admin account)
```

## Layout

- `app/` routes; everything under `app/(app)/` requires sign-in.
- `src/components/ui` shared controls (buttons, fields, data table, dialog, indicators).
- `src/components/{layout,video,charts,map}` app shell, MJPEG streams, Recharts, Leaflet.
- `src/api` REST client, Supabase auth client, report downloads.
- `src/context` auth (role, camera access, media ticket) and theme; `src/hooks` polling, WebSocket, URL state.

## Design tokens

Colours, type scale and radii live in `app/globals.css`: warm neutral greys, a single teal
accent, and desaturated risk colours that are always paired with a written label. Light and
dark palettes share token names; the theme is set on `<html data-theme>` before first paint.
Charts and the map read resolved colours through `useChartColors`.
