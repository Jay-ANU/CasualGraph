const http = require('http');

const FRONTEND = { hostname: '127.0.0.1', port: 3000 };
const BACKEND = { hostname: '127.0.0.1', port: 8000 };
const PORT = Number(process.env.NGROK_PROXY_PORT || 3001);

const BACKEND_PREFIXES = [
  '/auth',
  '/documents',
  '/extract',
  '/graph',
  '/health',
  '/kg-api',
  '/kg-static',
  '/kg-view',
  '/pipeline',
  '/rag',
];

function routeFor(url) {
  const pathname = new URL(url, 'http://localhost').pathname;
  return BACKEND_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
    ? BACKEND
    : FRONTEND;
}

const server = http.createServer((req, res) => {
  const target = routeFor(req.url || '/');
  const headers = { ...req.headers, host: `${target.hostname}:${target.port}` };

  const proxyReq = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: req.url,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (error) => {
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'proxy_error', message: error.message }));
  });

  req.pipe(proxyReq);
});

server.on('upgrade', (req, socket, head) => {
  const pathname = new URL(req.url || '/', 'http://localhost').pathname;
  if (pathname === '/ws') {
    socket.write('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
    socket.destroy();
    return;
  }

  const target = routeFor(req.url || '/');
  const headers = { ...req.headers, host: `${target.hostname}:${target.port}` };
  const proxyReq = http.request({
    hostname: target.hostname,
    port: target.port,
    method: req.method,
    path: req.url,
    headers,
  });

  proxyReq.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    socket.write(
      `HTTP/${proxyRes.httpVersion} ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n` +
        Object.entries(proxyRes.headers)
          .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
          .join('\r\n') +
        '\r\n\r\n'
    );
    proxySocket.write(proxyHead);
    socket.write(head);
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });

  proxyReq.on('error', () => socket.destroy());
  proxyReq.end();
});

server.listen(PORT, () => {
  console.log(`ngrok dev proxy listening on http://127.0.0.1:${PORT}`);
});
