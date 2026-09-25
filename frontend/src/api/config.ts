/** Explicit override, local development, or the same-origin production proxy. */
export const apiBase = (): string => {
  const configured = String(import.meta.env.VITE_API_BASE || '').trim();
  if (configured) return configured.replace(/\/+$/, '');
  const host = typeof window !== 'undefined' ? window.location.hostname || '127.0.0.1' : '127.0.0.1';
  return host === 'localhost' || host === '127.0.0.1' ? `http://${host}:8000` : '/api';
};
