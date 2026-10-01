import { pick } from '../../i18n/core';

// Upload jobs report their stage and status message in English. Known ones are
// shown in Chinese; anything else is shown as the server wrote it.
const STAGES_ZH: Record<string, string> = {
  queued: '排队中',
  starting: '启动中',
  reading: '读取中',
  cleaning: '清洗中',
  chunking: '分段中',
  embedding: '索引中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  rejected: '已拒绝',
};

const MESSAGES_ZH: Record<string, string> = {
  'Queued for processing': '已排队，等待处理',
  'Job queued': '任务已排队',
  'Next in queue, starting shortly': '即将开始处理',
  'Starting ingestion': '开始处理文档',
  'Reading uploaded content': '正在读取上传的内容',
  'Cleaning extracted text': '正在清洗提取的文本',
  'Splitting document into chunks': '正在将文档切分为段落',
  'Building vector index': '正在建立向量索引',
  'Processing document': '正在处理文档',
  'Document processing complete': '文档处理完成',
  'Duplicate detected; reusing existing document': '检测到重复文档，将复用已有文档',
  'Document processing failed': '文档处理失败',
  'Document processing did not return a result': '文档处理未返回结果',
  'Upload request was rejected': '上传请求被拒绝',
  'Upload request was rejected.': '上传请求被拒绝。',
  'Upload job was created without a job id.': '上传任务已创建，但缺少任务 ID。',
  'Unknown error': '未知错误',
};

const MATCHED_BY_ZH: Record<string, string> = {
  raw_hash: '文件哈希',
  text_hash: '文本哈希',
};

const lookup = (table: Record<string, string>, key: string): string | undefined => (
  Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined
);

const stageInChinese = (stage: string) => lookup(STAGES_ZH, stage) || stage;

/** A status message from an upload job ("Building vector index" / "正在建立向量索引"). */
export const formatUploadMessage = (message: string): string => {
  const queue = message.match(/^Waiting in queue \(position (\d+), (\d+) ahead\)$/);
  const zh = queue ? `排队中（第 ${queue[1]} 位，前面还有 ${queue[2]} 个任务）` : lookup(MESSAGES_ZH, message);
  return zh ? pick(zh, message) : message;
};

/** The upload button while a job runs ("Chunking…" / "分段中…"). */
export const formatUploadButtonLabel = (stage: string): string => (
  stage
    ? pick(`${stageInChinese(stage)}…`, `${stage.charAt(0).toUpperCase()}${stage.slice(1)}…`)
    : pick('处理中…', 'Processing…')
);

/** The progress line under the upload form: the job's message, else its stage. */
export const formatUploadProgress = (message: string, stage: string): string => {
  if (message) return formatUploadMessage(message);
  if (stage) return pick(stageInChinese(stage), stage);
  return pick('处理中', 'Processing');
};

/** The banner shown on the other tabs while a document is indexed. */
export const formatUploadBanner = (title: string, stage: string): string => pick(
  `正在建立索引：${title} · ${stage ? stageInChinese(stage) : '处理中'}`,
  `Indexing ${title} · ${stage || 'processing'}`,
);

/** How a duplicate upload was recognised ("text_hash" / "文本哈希"). */
export const formatDuplicateMatch = (matchedBy: string): string => pick(
  lookup(MATCHED_BY_ZH, matchedBy) || matchedBy || '内容哈希',
  matchedBy || 'content hash',
);
