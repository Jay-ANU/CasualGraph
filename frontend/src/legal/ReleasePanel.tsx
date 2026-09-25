import { useState } from 'react';
import { Check, Download } from 'lucide-react';
import type { Contract, Review } from './types';
import { ic } from './icon';

function StepDot({ n, done }: { n: number; done: boolean }) {
  return <span className="lv-step-dot" aria-hidden="true">{done ? <Check {...ic} size={12} strokeWidth={2.5} /> : n}</span>;
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
      <div><strong>选择要写入的修改</strong>
        <p>{selected.length ? `已采纳 ${selected.length} 项${drafts ? `，其中 ${drafts} 项是待复核的手工修改` : ''}。只有采纳的修改会写入。` : '在上方的意见中点“接受修改”。'}</p></div>
    </li>
    <li className={approved || verified ? 'done' : selected.length ? 'current' : ''}>
      <StepDot n={2} done={approved || verified} />
      <div><strong>核验修改组合</strong>
        <p>检查这些修改放在一起是否互相冲突、是否与合同其他条款一致。</p>
        {!approved && <>
          <label className="lv-check"><input type="checkbox" checked={externalConsent} disabled={busy} onChange={e => setExternalConsent(e.target.checked)} />
            <span>同意将已选修改（脱敏版本）发送给原审查模型进行核验。</span></label>
          <button className="lv-secondary" disabled={busy || !externalConsent || !selected.length} onClick={onCheck}>核验所选修订</button>
        </>}
        {checked && !approved && <div className={`lv-check-result ${verified ? 'is-ok' : 'is-warn'}`} role="status">
          <strong>{verified ? '核验完成，请你最后确认' : '核验没有通过，暂时不能导出修订稿'}</strong>
          <p>{checked.whole_contract.reason}</p>
          {checked.checks.map(item => <p key={item.finding_id}>{item.status === 'supported' ? '已比对' : '待处理'}：{item.reason}</p>)}
          {checked.missing_facts.map((item, i) => <p key={i} className="lv-note is-warn">{item}</p>)}
        </div>}
      </div>
    </li>
    <li className={approved ? 'done' : verified ? 'current' : ''}>
      <StepDot n={3} done={approved} />
      <div><strong>确认修订组合</strong>
        {approved ? <p role="status">已确认。之后如果更改任何决定，需要重新核验。这一步不代表企业审批或签署。</p>
          : verified ? <>
            <label className="lv-check"><input type="checkbox" checked={humanConsent} disabled={busy} onChange={e => setHumanConsent(e.target.checked)} />
              <span>我已核对全部已选修改及剩余风险，确认生成修订稿。</span></label>
            <button className="lv-primary" disabled={busy || !humanConsent} onClick={() => checked && onApprove(checked.fingerprint)}>确认当前修订组合</button>
          </> : <p>核验通过后，在这里做最后确认。</p>}
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
    <div className="lv-export-grid">
      <article className="lv-export-card">
        <h3>审查报告</h3>
        <p>全部意见、依据和你的处理决定，随时可以导出。</p>
        <button className="lv-secondary" disabled={busy} onClick={onReport}><Download {...ic} />导出审查报告</button>
      </article>
      <article className="lv-export-card is-main">
        <h3>{docx ? 'Word 修订稿' : '文字修改稿'}</h3>
        <p>{docx ? '把采纳的修改以修订痕迹写入原 Word 文件，可以在 Word 的“审阅”中逐项接受或拒绝。' : '把采纳的修改写入合同文字。它不是 Word 修订文件，请对照原合同复核。'}</p>
        <DraftRelease key={`${review.id}-${JSON.stringify(review.decisions)}`} review={review} busy={busy} onCheck={onCheck} onApprove={onApprove} />
        <div className="lv-export-action">
          <button className="lv-primary" disabled={busy || !review.draft_approval || !accepted} onClick={onDraft}><Download {...ic} />{docx ? '导出 Word 修订稿' : '导出文字修改稿'}</button>
          <span>{accepted} 项修改已选入修订稿</span>
        </div>
      </article>
    </div>
    <p className="lv-hint">修订稿含真实信息和被删除的内容，不是脱敏副本；分享前请确认接收人。导出不会签署合同，也不会覆盖你的原文件。</p>
  </section>;
}
