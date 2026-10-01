import { useState } from 'react';
import type { CSSProperties } from 'react';
import { ChevronRight, Lock, Search, ShieldCheck, Upload, UserCheck } from 'lucide-react';
import type { ContractSummary } from './types';
import { contractStatusLabel, fileTitle, formatDate } from './labels';
import { ContractSheet } from './art';
import { ic } from './icon';
import { useI18n } from '../i18n/core';

const STATUS_TONE: Record<string, string> = {
  redaction_pending: 'is-mid', ready: 'is-ok', queued: 'is-ink', running: 'is-ink', partial: 'is-mid', failed: 'is-high',
};
const WAITING = ['redaction_pending', 'ready'];
const formatOf = (name: string) => name.match(/\.(docx|pdf|txt)$/i)?.[1].toUpperCase() || '';

/** The desk's home: drop a contract to start, or reopen one from the matter's library. */
export function Library({ contracts, matterName, loading, disabled, busy, query, onQuery, onUpload, onDrop, onOpen }: {
  contracts: ContractSummary[]; matterName?: string; loading: boolean; disabled: boolean; busy: boolean; query: string;
  onQuery: (value: string) => void; onUpload: () => void; onDrop: (files: FileList) => void; onOpen: (id: string) => void;
}) {
  const { tx } = useI18n();
  const [dragging, setDragging] = useState(false);
  const text = query.trim().toLocaleLowerCase();
  const shown = contracts.filter(c => c.name.toLocaleLowerCase().includes(text));
  const waiting = contracts.filter(c => WAITING.includes(c.status)).length;
  return <main id="legal-main" tabIndex={-1} className="lv-library">
    <div className="lv-library-inner">
      <header className="lv-library-head">
        <div>
          <h1>{tx('合同库', 'Contract library')}</h1>
          <p className="lv-library-meta">{matterName && <>{matterName}<span className="lv-sep" aria-hidden="true">|</span></>}
            <span className="lv-mono">{contracts.length}</span>{tx(' 份合同', contracts.length === 1 ? ' contract' : ' contracts')}{waiting > 0 && <>{tx('，', ', ')}<span className="lv-mono">{waiting}</span>{tx(' 份待处理', ' to process')}</>}</p>
        </div>
        {contracts.length > 0 && <label className="lv-search"><Search {...ic} size={15} />
          <input aria-label={tx('搜索合同', 'Search contracts')} placeholder={tx('搜索合同名称', 'Search by name')} value={query} onChange={e => onQuery(e.target.value)} /></label>}
      </header>
      <section className={`lv-upload ${dragging ? 'is-dragging' : ''} ${disabled ? 'is-disabled' : ''}`} aria-label={tx('上传合同', 'Upload a contract')}
        onClick={e => { if (!disabled && !(e.target as HTMLElement).closest('button')) onUpload(); }}
        onDragOver={e => { e.preventDefault(); if (!disabled && e.dataTransfer.types.includes('Files')) setDragging(true); }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={e => { e.preventDefault(); setDragging(false); if (!disabled) onDrop(e.dataTransfer.files); }}>
        <ContractSheet size={54} active={dragging} />
        <div className="lv-upload-copy">
          <p className="lv-upload-title">{dragging ? tx('松开以上传', 'Drop to upload') : tx('拖入合同，开始新的审查', 'Drop a contract here to start a review')}</p>
          <p className="lv-upload-spec">{tx('.docx、文本型 .pdf、.txt · 单个文件不超过 10 MB', '.docx, text-based .pdf or .txt · up to 10 MB per file')}</p>
          <ul className="lv-assurances" aria-label={tx('隐私保护', 'Privacy safeguards')}>
            <li><ShieldCheck {...ic} size={14} />{tx('自动脱敏', 'Automatic redaction')}</li>
            <li><Lock {...ic} size={14} />{tx('加密存储', 'Encrypted storage')}</li>
            <li><UserCheck {...ic} size={14} />{tx('模型分析需单独授权', 'Model analysis only with your consent')}</li>
          </ul>
        </div>
        <button type="button" id="legal-upload-button" className="lv-primary lv-upload-cta" disabled={disabled} onClick={onUpload}><Upload {...ic} size={15} />{tx('选择文件', 'Choose file')}</button>
      </section>
      <section className="lv-recent" aria-labelledby="legal-recent-title">
        <h2 id="legal-recent-title">{tx('最近', 'Recent')}</h2>
        <div className="lv-table-head" aria-hidden="true"><span>{tx('合同', 'Contract')}</span><span>{tx('状态', 'Status')}</span><span>{tx('更新', 'Updated')}</span><span /></div>
        <ul className="lv-table">
          {shown.map((item, i) => <li key={item.id} style={{ '--i': Math.min(i, 12) } as CSSProperties}>
            <button className="lv-table-row" disabled={busy} onClick={() => onOpen(item.id)}>
              <span className="lv-table-name"><strong>{fileTitle(item.name)}</strong><small>{formatOf(item.name)}</small></span>
              <span><span className={`lv-status ${STATUS_TONE[item.status] || ''}`}><i aria-hidden="true" />{contractStatusLabel(item.status)}</span></span>
              <span className="lv-mono lv-table-date">{formatDate(item.created_at) || '—'}</span>
              <ChevronRight {...ic} className="lv-table-go" />
            </button>
          </li>)}
        </ul>
        {!loading && !contracts.length && <p className="lv-table-empty">{tx('暂无合同', 'No contracts yet')}</p>}
        {contracts.length > 0 && !shown.length && <p className="lv-table-empty" role="status">{tx('没有匹配的合同', 'No matching contracts')}</p>}
      </section>
      <p className="lv-footnote">{tx('审查结果仅供参考，不构成法律意见。', 'Review results are for reference only and are not legal advice.')}</p>
    </div>
  </main>;
}
