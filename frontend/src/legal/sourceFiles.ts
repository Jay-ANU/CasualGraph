import { apiBase } from '../api/config';
import { withAuth } from '../api/client';

export type SourceKind = 'image' | 'pdf';
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/avif', 'image/bmp', 'image/x-ms-bmp']);

/** No bearer URL, HTML, SVG, or external document resources ever enter a source element. */
export async function sourceBlob(path: string, kind: SourceKind, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${apiBase()}${path}`, withAuth({ signal }));
  if (!response.ok) throw new Error('unavailable');
  const blob = await response.blob();
  const type = blob.type.split(';')[0].toLowerCase();
  if (kind === 'pdf' ? type !== 'application/pdf' : !IMAGE_TYPES.has(type)) throw new Error('unsupported');
  return blob;
}
