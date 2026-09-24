import type { RagStreamEvent } from '../types/api';
import { apiBase } from './config';
import { jsonRequest, readApiError, withAuth } from './client';

/**
 * POSTs a JSON body to a server-sent-events endpoint and returns the open
 * response, whose body `readSseEvents` then consumes. A non-2xx status throws
 * an ApiError before any event is read.
 */
export const openEventStream = async (path: string, body: unknown): Promise<Response> => {
  const response = await fetch(`${apiBase()}${path}`, withAuth(jsonRequest('POST', body)));
  if (!response.ok) throw await readApiError(response);
  return response;
};

export const readSseEvents = async (
  response: Response,
  onEvent: (event: RagStreamEvent) => void,
): Promise<void> => {
  if (!response.body) {
    throw new Error('Streaming response body is empty');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const trimmed = frame.trim();
      if (!trimmed || trimmed.startsWith(':')) {
        continue;
      }
      const dataLine = trimmed
        .split('\n')
        .find((line) => line.startsWith('data:'));
      if (!dataLine) {
        continue;
      }
      const payload = dataLine.slice(5).trim();
      if (!payload) {
        continue;
      }
      onEvent(JSON.parse(payload) as RagStreamEvent);
    }

    if (done) {
      break;
    }
  }
};
