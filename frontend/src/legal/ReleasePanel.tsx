import { useState } from 'react';
import { Check } from 'lucide-react';
import type { Contract, Review } from './types';
import { ic } from './icon';

function StepDot({ n, done }: { n: number; done: boolean }) {
  return <span className="lv-step-dot" aria-hidden="true">{done ? <Check {...ic} size={11} strokeWidth={3} /> : n}</span>;
}

/** Selected edits are checked as one combination, then confirmed by a person, before a redline can be exported. */
function DraftRelease({ review, busy, onCheck, onApprove }: {
  review: Review; busy: boolean; onCheck: () => void; onApprove: (fingerprint: string) => void;
}) {
  const [externalConsent, setExternalConsent] = useState(false);
  const [humanConsent, setHumanConsent] = useState(false);
  const selected = Object.values(review.decisions).filter(d => ['accepted', 'draft'].includes(d.decision));
  const drafts = selected.filter(d => d.decision === 'draft').length;
  const checked = review.draft_check;
  const approved = Boolean(review.draft_approval);
  const verified = checked?.status === 'verified';
  return <ol className="lv-release-steps" aria-label="最终修订组合核验">
    <li className={selected.length ? 'done' : 'current'}>
      <StepDot n={1} done={selected.length > 0} />
      <div><strong>采纳修改</strong>
        <p>{selected.length ? `已采纳 ${selected.length} 项${drafts ? `（含人工修订 ${drafts} 项）` : ''}` : '尚未采纳任何修改'}</p></div>
    </li>
    <li className={approved || verified ? 'done' : selected.length ? 'current' : ''}>
      <StepDot n={2} done={approved || verified} />
      <div><strong>组合核验</strong>
        {!approved && !verified && selected.length > 0 && <>
          <label className="lv-check lv-check-sm"><input type="checkbox" checked={externalConsent} disabled={busy} onChange={e => setExternalConsent(e.target.checked)} />
            <span>同意将已采纳修改（脱敏）提交原审查模型核验</span></label>
          <button className="lv-secondary lv-btn-sm" disabled={busy || !externalConsent} onClick={onCheck}>开始核验</button>
        </>}
        {checked && !approved && <div className={`lv-check-result ${verified ? 'is-ok' : 'is-warn'}`} role="status">
          <strong>{verified ? '核验通过' : '核验未通过，暂不可导出'}</strong>
          {!verified && <p>{checked.whole_contract.reason}</p>}
          {!verified && checked.checks.filter(item => item.status !== 'supported').map(item => <p key={item.finding_id}>{item.reason}</p>)}
          {checked.missing_facts.map((item, i) => <p key={i}>{item}</p>)}
        </div>}
      </div>
    </li>
    <li className={approved ? 'done' : verified ? 'current' : ''}>
      <StepDot n={3} done={approved} />
      <div><strong>确认修订</strong>
        {approved ? <p role="status">已确认。修改决定变更后需重新核验。</p>
          : verified && <>
            <label className="lv-check lv-check-sm"><input type="checkbox" checked={humanConsent} disabled={busy} onChange={e => setHumanConsent(e.target.checked)} />
              <span>已核对全部修改及剩余风险，确认生成修订版</span></label>
            <button className="lv-primary lv-btn-sm" disabled={busy || !humanConsent} onClick={() => checked && onApprove(checked.fingerprint)}>确认修订</button>
          </>}
      </div>
    </li>
  </ol>;
}

export function ReleasePanel({ review, contract, busy, onCheck, onApprove, onReport, onDraft }: {
  review: Review; contract: Contract; busy: boolean;
  onCheck: () => void; onApprove: (fingerprint: string) => void; onReport: () => void; onDraft: () => void;
}) {
  const docx = contract.format === 'docx';
  const accepted = Object.values(review.decisions).filter(d => d.decision === 'accepted').length;
  return <section id="legal-release" className="lv-release" aria-labelledby="legal-release-title">
    <div className="lv-section-head"><h2 id="legal-release-title">导出</h2></div>
    <div className="lv-export-list">
      <div className="lv-export-row">
        <div><strong>审查报告</strong><span>审查意见、依据及处理结果</span></div>
        <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onReport}>导出报告</button>
      </div>
      <div className="lv-export-row">
        <div><strong>{docx ? 'Word 修订版' : '修订文本'}</strong><span>{docx ? '以修订痕迹写入原文件' : '纯文本，不含修订痕迹'}</span></div>
        <button className="lv-primary lv-btn-sm" disabled={busy || !review.draft_approval || !accepted} onClick={onDraft}>{docx ? '导出 Word 修订版' : '导出修订文本'}</button>
      </div>
      <DraftRelease key={`${review.id}-${JSON.stringify(review.decisions)}`} review={review} busy={busy} onCheck={onCheck} onApprove={onApprove} />
    </div>
  </section>;
}
