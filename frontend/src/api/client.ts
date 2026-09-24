import { apiBase } from './config';

/** localStorage key of the bearer token. AuthContext writes it when a user signs in. */
export const TOKEN_STORAGE_KEY = 'token';

/** A request that reached the API and failed, with the server's own message when it sent one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

interface ErrorPayload {
  error?: unknown;
  message?: unknown;
  detail?: unknown;
}

const NO_ACCESSIBLE_DOCUMENTS =
  'No searchable documents are available for this account yet. Upload a document, or try again once the shared library is indexed.';

const HTML_RESPONSE_HINT =
  'The response was HTML, so check that VITE_API_BASE points to the backend API rather than the frontend.';

const asText = (value: unknown): string => (typeof value === 'string' ? value : '');

const statusLine = (response: Response) =>
  `The server returned ${response.status}${response.statusText ? ` ${response.statusText}` : ''}.`;

const looksLikeHtml = (raw: string) => {
  const trimmed = raw.trim();
  return trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html');
};

/** Turns a failed response into an ApiError. */
export const readApiError = async (response: Response): Promise<ApiError> => {
  const fallback = statusLine(response);
  let raw: string;
  try {
    raw = await response.text();
  } catch {
    return new ApiError(response.status, fallback);
  }
  if (!raw.trim()) return new ApiError(response.status, fallback);

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return new ApiError(response.status, looksLikeHtml(raw) ? `${fallback} ${HTML_RESPONSE_HINT}` : raw.slice(0, 240));
  }

  const payload: ErrorPayload = parsed && typeof parsed === 'object' ? parsed : {};
  const detail = payload.detail;
  const detailObject: ErrorPayload | undefined = detail && typeof detail === 'object' ? detail : undefined;
  const code = asText(payload.error) || asText(detailObject?.error) || undefined;
  if (code === 'no_accessible_documents') return new ApiError(response.status, NO_ACCESSIBLE_DOCUMENTS, code);
  if (typeof detail === 'string') return new ApiError(response.status, detail, code);
  if (detailObject) {
    return new ApiError(response.status, asText(detailObject.message) || asText(detailObject.error) || fallback, code);
  }
  return new ApiError(response.status, asText(payload.message) || asText(payload.error) || fallback, code);
};

const storedToken = (): string | null => {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
};

/** Adds the signed-in user's bearer token, unless the caller set an Authorization header. */
export const withAuth = (init: RequestInit = {}): RequestInit => {
  const headers = new Headers(init.headers);
  const token = storedToken();
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
  return { ...init, headers };
};

/** Options for a request with a JSON body. */
export const jsonRequest = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

/**
 * Calls the backend: prefixes the API base, sends the bearer token, parses the
 * JSON reply and throws an ApiError for any non-2xx status.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, withAuth(init));
  if (!response.ok) throw await readApiError(response);
  const raw = await response.text();
  if (!raw.trim()) return undefined as T;
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new ApiError(
      response.status,
      looksLikeHtml(raw) ? `${statusLine(response)} ${HTML_RESPONSE_HINT}` : 'The server sent a reply that is not JSON.',
      'invalid_response',
    );
  }
}
