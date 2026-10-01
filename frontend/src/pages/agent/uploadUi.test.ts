import { setCurrentLang } from '../../i18n/core';
import {
  formatDuplicateMatch,
  formatUploadBanner,
  formatUploadButtonLabel,
  formatUploadMessage,
  formatUploadProgress,
} from './uploadUi';

describe('upload status text', () => {
  beforeEach(() => setCurrentLang('en'));
  afterEach(() => setCurrentLang('zh'));

  it('shows the job stage and message exactly as before in English', () => {
    expect(formatUploadButtonLabel('chunking')).toBe('Chunking…');
    expect(formatUploadButtonLabel('')).toBe('Processing…');
    expect(formatUploadProgress('Building vector index', 'embedding')).toBe('Building vector index');
    expect(formatUploadProgress('', 'embedding')).toBe('embedding');
    expect(formatUploadProgress('', '')).toBe('Processing');
    expect(formatUploadBanner('Lease.pdf', '')).toBe('Indexing Lease.pdf · processing');
    expect(formatDuplicateMatch('')).toBe('content hash');
    expect(formatDuplicateMatch('text_hash')).toBe('text_hash');
  });

  it('translates known stages and server messages into Chinese', () => {
    setCurrentLang('zh');
    expect(formatUploadButtonLabel('chunking')).toBe('分段中…');
    expect(formatUploadProgress('Building vector index', 'embedding')).toBe('正在建立向量索引');
    expect(formatUploadProgress('', 'embedding')).toBe('索引中');
    expect(formatUploadMessage('Waiting in queue (position 3, 2 ahead)')).toBe('排队中（第 3 位，前面还有 2 个任务）');
    expect(formatUploadBanner('Lease.pdf', 'reading')).toBe('正在建立索引：Lease.pdf · 读取中');
    expect(formatDuplicateMatch('raw_hash')).toBe('文件哈希');
  });

  it('shows unknown stages and messages as the server wrote them', () => {
    setCurrentLang('zh');
    expect(formatUploadButtonLabel('ocr')).toBe('ocr…');
    expect(formatUploadMessage('File type not allowed')).toBe('File type not allowed');
    expect(formatUploadMessage('constructor')).toBe('constructor');
  });
});
