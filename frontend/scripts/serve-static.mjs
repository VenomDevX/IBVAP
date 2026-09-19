import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer, request as httpRequest } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';

const root = resolve(process.env.STATIC_DIR || 'out');
const port = Number(process.env.PORT || 3001);
const backend = new URL(process.env.BACKEND_URL || 'http://127.0.0.1:8002');
const types = {
  '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ico': 'image/x-icon',
};

const proxyPrefixes = ['/api/', '/snapshots/', '/static/'];
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url || '/', 'http://localhost').pathname);
  if (proxyPrefixes.some(prefix => pathname.startsWith(prefix))) {
    const upstream = httpRequest({
      hostname: backend.hostname, port: backend.port, method: request.method,
      path: request.url, headers: { ...request.headers, host: backend.host },
    }, upstreamResponse => {
      upstreamResponse.on('error', () => response.destroy());
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    });
    upstream.on('error', () => {
      if (response.headersSent) response.destroy();
      else response.writeHead(502, { 'Content-Type': 'application/json' }).end('{"detail":"Backend unavailable"}');
    });
    // A browser leaving the page resets long-lived MJPEG sockets (ECONNRESET).
    // Without these handlers that error is unhandled and kills the server.
    request.on('error', () => upstream.destroy());
    response.on('error', () => upstream.destroy());
    response.on('close', () => upstream.destroy());
    request.pipe(upstream);
    return;
  }
  let target = resolve(join(root, normalize(pathname)));
  if (!target.startsWith(root)) { response.writeHead(403).end('Forbidden'); return; }
  if (existsSync(target) && statSync(target).isDirectory()) target = join(target, 'index.html');
  if (!existsSync(target)) target = join(root, 'index.html');
  response.setHeader('Content-Type', types[extname(target)] || 'application/octet-stream');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.on('error', () => {});
  createReadStream(target).on('error', () => response.destroy()).pipe(response);
});

server.on('upgrade', (request, socket, head) => {
  socket.on('error', () => socket.destroy());
  const upstream = httpRequest({ hostname: backend.hostname, port: backend.port, method: 'GET', path: request.url, headers: { ...request.headers, host: backend.host } });
  upstream.on('upgrade', (response, upstreamSocket, upstreamHead) => {
    upstreamSocket.on('error', () => socket.destroy());
    socket.on('close', () => upstreamSocket.destroy());
    socket.write(`HTTP/1.1 101 Switching Protocols\r\n${Object.entries(response.headers).map(([key, value]) => `${key}: ${value}`).join('\r\n')}\r\n\r\n`);
    if (head.length) upstreamSocket.write(head);
    if (upstreamHead.length) socket.write(upstreamHead);
    upstreamSocket.pipe(socket).pipe(upstreamSocket);
  });
  upstream.on('error', () => socket.destroy());
  upstream.end();
});

server.on('clientError', (_error, socket) => socket.destroy());

server.listen(port, '0.0.0.0', () => console.log(`IBVAP frontend listening on http://localhost:${port} (backend ${backend.origin})`));
