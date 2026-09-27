import { useState } from 'react';
import { FileDown, FileText } from 'lucide-react';
import type { Contract, Review } from './types';
import type { Numbered } from './workspace';
import { isRevised } from './workspace';
import { Marker } from './Marker';
import { DrawnCheck, Spinner } from './ui';
import { ic } from './icon';

function StepDot({ n, state }: { n: number; state: 'done' | 'current' | 'todo' }) {
  return <span className={`lv-release-dot is-${state}`} aria-hidden="true">{state === 'done' ? <DrawnCheck size={11} /> : n}</span>;
}

/** Selected edits are checked as one combination, then confirmed by a person, before a redline can be exported. */
function DraftRelease({ review, adopted, busy, onCheck, onApprove, onBack }: {
  review: Review; adopted: Numbered[]; busy: boolean; onCheck: () => void; onApprove: (fingerprint: string) => void; onBack: () => void;
}) {
  const [externalConsent, setExternalConsent] = useState(false);
  const [humanConsent, setHumanConsent] = useState(false);
  const drafts = adopted.filter(x => review.decisions[x.finding.id]?.decision === 'draft').length;
  const checked = review.draft_check;
  const approved = Boolean(review.draft_approval);
  const verified = checked?.status === 'verified';
  const selected = adopted.length > 0;
  return <ol className="lv-release-steps" aria-label="修订版核验">
    <li className={selected ? 'is-done' : 'is-current'}>
      <StepDot n={1} state={selected ? 'done' : 'current'} />
      <div><strong>采纳修改</strong>
        <p>{selected ? `已采纳 ${adopted.length} 项${drafts ? `（含人工修订 ${drafts} 项）` : ''}` : '尚未采纳任何修改'}</p>
        <div className="lv-release-marks">{adopted.map(x => <Marker key={x.finding.id} n={x.n} finding={x.finding} state="revised" size="sm" number />)}
          <button className="lv-text-button" onClick={onBack}>返回处理</button></div>
      </div>
    </li>
    <li className={approved || verified ? 'is-done' : selected ? 'is-current' : ''}>
      <StepDot n={2} state={approved || verified ? 'done' : selected ? 'current' : 'todo'} />
      <div><strong>组合核验</strong>
        {!selected && <p>采纳修改后可核验</p>}
        {!approved && !verified && selected && <>
          <label className="lv-check lv-check-sm"><input type="checkbox" checked={externalConsent} disabled={busy} onChange={e => setExternalConsent(e.target.checked)} />
            <span>同意将已采纳修改（脱敏）提交原审查模型核验</span></label>
          <button className="lv-secondary lv-btn-sm" disabled={busy || !externalConsent} onClick={onCheck}>{busy && <Spinner />}开始核验</button>
        </>}
        {checked && !approved && <div className={`lv-check-result ${verified ? 'is-ok' : 'is-warn'}`} role="status">
          <strong>{verified ? '核验通过' : '核验未通过，暂不可导出'}</strong>
          {!verified && <p>{checked.whole_contract.reason}</p>}
          {!verified && checked.checks.filter(item => item.status !== 'supported').map(item => <p key={item.finding_id}>{item.reason}</p>)}
          {checked.missing_facts.map((item, i) => <p key={i}>{item}</p>)}
        </div>}
      </div>
    </li>
    <li className={approved ? 'is-done' : verified ? 'is-current' : ''}>
      <StepDot n={3} state={approved ? 'done' : verified ? 'current' : 'todo'} />
      <div><strong>确认修订</strong>
        {approved ? <p role="status">已确认。修改决定变更后需重新核验。</p>
          : verified ? <>
            <label className="lv-check lv-check-sm"><input type="checkbox" checked={humanConsent} disabled={busy} onChange={e => setHumanConsent(e.target.checked)} />
              <span>已核对全部修改及剩余风险，确认生成修订版</span></label>
            <button className="lv-primary lv-btn-sm" disabled={busy || !humanConsent} onClick={() => checked && onApprove(checked.fingerprint)}>确认修订</button>
          </> : <p>核验通过后确认</p>}
      </div>
    </li>
  </ol>;
}

export function ReleasePanel({ review, contract, open, busy, onCheck, onApprove, onReport, onDraft, onBack }: {
  review: Review; contract: Contract; open: Numbered[]; busy: boolean;
  onCheck: () => void; onApprove: (fingerprint: string) => void; onReport: () => void; onDraft: () => void; onBack: () => void;
}) {
  const docx = contract.format === 'docx';
  const adopted = open.filter(x => isRevised(review.decisions[x.finding.id]));
  const accepted = adopted.some(x => review.decisions[x.finding.id]?.decision === 'accepted');
  return <section id="legal-release" className="lv-rail-panel" aria-labelledby="legal-release-title">
    <div className="lv-rail-head">
      <h2 id="legal-release-title">导出</h2>
      <p>报告可随时导出；修订版需核验并确认后生成。</p>
    </div>
    <div className="lv-rail-body">
      <div className="lv-export-list">
        <div className="lv-export-row">
          <FileText {...ic} size={18} />
          <div><strong>审查报告</strong><span>意见、依据及处理结果 · Markdown</span></div>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onReport}>导出报告</button>
        </div>
        <div className="lv-export-row">
          <FileDown {...ic} size={18} />
          <div><strong>{docx ? 'Word 修订版' : '修订文本'}</strong><span>{docx ? '以修订痕迹写入原文件 · DOCX' : '纯文本，不含修订痕迹 · TXT'}</span></div>
          <button className="lv-primary lv-btn-sm" disabled={busy || !review.draft_approval || !accepted} onClick={onDraft}>{docx ? '导出 Word 修订版' : '导出修订文本'}</button>
        </div>
      </div>
      <DraftRelease key={`${review.id}-${JSON.stringify(review.decisions)}`} review={review} adopted={adopted} busy={busy} onCheck={onCheck} onApprove={onApprove} onBack={onBack} />
      <p className="lv-footnote">审查结果仅供参考，不构成法律意见。</p>
    </div>
  </section>;
}

