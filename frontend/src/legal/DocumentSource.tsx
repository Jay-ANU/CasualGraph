import { useEffect, useState } from 'react';
import { useI18n } from '../i18n/core';
import { sourceBlob, type SourceKind } from './sourceFiles';

/** Only mounted after an explicit original-view action. Revoke bytes on close or contract switch. */
function useSourceUrl(path: string, kind: SourceKind) {
  const [loaded, setLoaded] = useState<{ path: string; url: string; error: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let url = '';
    void sourceBlob(path, kind, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setLoaded({ path, url, error: '' });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setLoaded({ path, url: '', error: error instanceof Error ? error.message : 'unavailable' });
    });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [path, kind]);
  return loaded?.path === path ? loaded : null;
}

export function OriginalImage({ contractId, assetId, width, height }: { contractId: string; assetId: string; width?: number; height?: number }) {
  const { tx } = useI18n();
  const source = useSourceUrl(`/legal/contracts/${encodeURIComponent(contractId)}/assets/${encodeURIComponent(assetId)}`, 'image');
  const [failedUrl, setFailedUrl] = useState('');
  if (!source) return <p className="lv-source-status" role="status">{tx('正在读取原件图片…', 'Loading the original image…')}</p>;
  if (source.error || failedUrl === source.url) return <p className="lv-source-status">{tx('此图片暂时无法预览，请下载原文件查看。', 'This image cannot be previewed. Download the original file to view it.')}</p>;
  return <img className="lv-source-image" src={source.url} alt={tx('原件中的图片（未脱敏）', 'Image in the original document (unredacted)')}
    style={width && width > 0 ? { width, aspectRatio: height && height > 0 ? `${width} / ${height}` : undefined, objectFit: 'contain' } : undefined}
    onError={() => setFailedUrl(source.url)} />;
}

export function OriginalPdf({ contractId, page = 1 }: { contractId: string; page?: number | null }) {
  const { tx } = useI18n();
  const source = useSourceUrl(`/legal/contracts/${encodeURIComponent(contractId)}/original`, 'pdf');
  if (!source) return <p className="lv-source-status" role="status">{tx('正在读取原 PDF…', 'Loading the original PDF…')}</p>;
  if (source.error) return <p className="lv-source-status">{tx('原 PDF 暂时无法预览，请下载原文件查看。', 'The original PDF cannot be previewed. Download the original file to view it.')}</p>;
  const currentPage = Number.isInteger(page) && Number(page) > 0 ? Number(page) : 1;
  return <div className="lv-original-pdf">
    <p className="lv-source-status">{tx(`原 PDF · 第 ${currentPage} 页。若浏览器无法显示，可下载原文件。`, `Original PDF · Page ${currentPage}. If your browser cannot display it, download the original file.`)}</p>
    <iframe key={`${source.url}-${currentPage}`} title={tx('原 PDF 页面', 'Original PDF pages')} src={`${source.url}#page=${currentPage}`} />
  </div>;
}
