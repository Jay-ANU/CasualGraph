/**
 * Origin of the backend API, without a trailing slash.
 *
 * Set `VITE_API_BASE` at build time (for example on Vercel). Without it, a page
 * opened on localhost talks to the API on port 8000 of the same host, and any
 * other host uses relative URLs (same origin).
 */
export const apiBase = (): string => {
  const configured = String(import.meta.env.VITE_API_BASE || '').trim();
  if (configured) return configured.replace(/\/+$/, '');
  const host = typeof window !== 'undefined' ? window.location.hostname || '127.0.0.1' : '127.0.0.1';
  return host === 'localhost' || host === '127.0.0.1' ? `http://${host}:8000` : '';
};
