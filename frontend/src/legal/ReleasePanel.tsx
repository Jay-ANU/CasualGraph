import { useState } from 'react';
import { FileDown, FileText } from 'lucide-react';
import type { Contract, Review } from './types';
import type { Numbered } from './workspace';
import { isRevised } from './workspace';
import { Marker } from './Marker';
import { DrawnCheck, Spinner } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { serverText } from './i18n';

function StepDot({ n, state }: { n: number; state: 'done' | 'current' | 'todo' }) {
  return <span className={`lv-release-dot is-${state}`} aria-hidden="true">{state === 'done' ? <DrawnCheck size={11} /> : n}</span>;
}

/** Selected edits are checked as one combination, then confirmed by a person, before a redline can be exported. */
function DraftRelease({ review, adopted, busy, onCheck, onApprove, onBack }: {
  review: Review; adopted: Numbered[]; busy: boolean; onCheck: () => void; onApprove: (fingerprint: string) => void; onBack: () => void;
}) {
  const { tx } = useI18n();
  const [externalConsent, setExternalConsent] = useState(false);
  const [humanConsent, setHumanConsent] = useState(false);
  const drafts = adopted.filter(x => review.decisions[x.finding.id]?.decision === 'draft').length;
  const checked = review.draft_check;
  const approved = Boolean(review.draft_approval);
  const verified = checked?.status === 'verified';
  const selected = adopted.length > 0;
  return <ol className="lv-release-steps" aria-label={tx('修订版核验', 'Revision check')}>
    <li className={selected ? 'is-done' : 'is-current'}>
      <StepDot n={1} state={selected ? 'done' : 'current'} />
      <div><strong>{tx('采纳修改', 'Accept edits')}</strong>
        <p>{selected ? tx(`已采纳 ${adopted.length} 项${drafts ? `（含人工修订 ${drafts} 项）` : ''}`, `${adopted.length} accepted${drafts ? ` (${drafts} manual)` : ''}`) : tx('尚未采纳任何修改', 'No edits accepted yet')}</p>
        <div className="lv-release-marks">{adopted.map(x => <Marker key={x.finding.id} n={x.n} finding={x.finding} state="revised" size="sm" number />)}
          <button className="lv-text-button" onClick={onBack}>{tx('返回处理', 'Back to notes')}</button></div>
      </div>
    </li>
    <li className={approved || verified ? 'is-done' : selected ? 'is-current' : ''}>
      <StepDot n={2} state={approved || verified ? 'done' : selected ? 'current' : 'todo'} />
      <div><strong>{tx('组合核验', 'Check the edits together')}</strong>
        {!selected && <p>{tx('采纳修改后可核验', 'Available once you accept an edit')}</p>}
        {!approved && !verified && selected && <>
          <label className="lv-check lv-check-sm"><input type="checkbox" checked={externalConsent} disabled={busy} onChange={e => setExternalConsent(e.target.checked)} />
            <span>{tx('同意将已采纳修改（脱敏）提交原审查模型核验', 'I agree to send the accepted edits (redacted) to the review model for checking')}</span></label>
          <button className="lv-secondary lv-btn-sm" disabled={busy || !externalConsent} onClick={onCheck}>{busy && <Spinner />}{tx('开始核验', 'Run check')}</button>
        </>}
        {checked && !approved && <div className={`lv-check-result ${verified ? 'is-ok' : 'is-warn'}`} role="status">
          <strong>{verified ? tx('核验通过', 'Check passed') : tx('核验未通过，暂不可导出', 'Check failed; export is blocked')}</strong>
          {!verified && <p>{serverText(checked.whole_contract.reason)}</p>}
          {!verified && checked.checks.filter(item => item.status !== 'supported').map(item => <p key={item.finding_id}>{serverText(item.reason)}</p>)}
          {checked.missing_facts.map((item, i) => <p key={i}>{serverText(item)}</p>)}
        </div>}
      </div>
    </li>
    <li className={approved ? 'is-done' : verified ? 'is-current' : ''}>
      <StepDot n={3} state={approved ? 'done' : verified ? 'current' : 'todo'} />
      <div><strong>{tx('确认修订', 'Confirm revision')}</strong>
        {approved ? <p role="status">{tx('已确认。修改决定变更后需重新核验。', 'Confirmed. Changing a decision means checking again.')}</p>
          : verified ? <>
            <label className="lv-check lv-check-sm"><input type="checkbox" checked={humanConsent} disabled={busy} onChange={e => setHumanConsent(e.target.checked)} />
              <span>{tx('已核对全部修改及剩余风险，确认生成修订版', 'I have checked every edit and the remaining risks, and confirm the revised version')}</span></label>
            <button className="lv-primary lv-btn-sm" disabled={busy || !humanConsent} onClick={() => checked && onApprove(checked.fingerprint)}>{tx('确认修订', 'Confirm revision')}</button>
          </> : <p>{tx('核验通过后确认', 'Confirm once the check passes')}</p>}
      </div>
    </li>
  </ol>;
}

export function ReleasePanel({ review, contract, open, busy, onCheck, onApprove, onReport, onDraft, onBack }: {
  review: Review; contract: Contract; open: Numbered[]; busy: boolean;
  onCheck: () => void; onApprove: (fingerprint: string) => void; onReport: () => void; onDraft: () => void; onBack: () => void;
}) {
  const { tx } = useI18n();
  const docx = contract.format === 'docx';
  const adopted = open.filter(x => isRevised(review.decisions[x.finding.id]));
  const accepted = adopted.some(x => review.decisions[x.finding.id]?.decision === 'accepted');
  return <section id="legal-release" className="lv-rail-panel" aria-labelledby="legal-release-title">
    <div className="lv-rail-head">
      <h2 id="legal-release-title">{tx('导出', 'Export')}</h2>
      <p>{tx('报告可随时导出；修订版需核验并确认后生成。', 'Export the report at any time; the revised contract needs a check and your confirmation first.')}</p>
    </div>
    <div className="lv-rail-body">
      <div className="lv-export-list">
        <div className="lv-export-row">
          <span className="lv-tile is-gray"><FileText {...ic} size={18} /></span>
          <div><strong>{tx('审查报告', 'Review report')}</strong><span>{tx('意见、依据及处理结果 · Markdown', 'Findings, basis and decisions · Markdown')}</span></div>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onReport}>{tx('导出报告', 'Export report')}</button>
        </div>
        <div className="lv-export-row">
          <span className="lv-tile is-gray"><FileDown {...ic} size={18} /></span>
          <div><strong>{docx ? tx('Word 修订版', 'Tracked-changes Word') : tx('修订文本', 'Revised text')}</strong>
            <span>{docx ? tx('以修订痕迹写入原文件 · DOCX', 'Edits as tracked changes in the original · DOCX') : tx('纯文本，不含修订痕迹 · TXT', 'Plain text without tracked changes · TXT')}</span></div>
          <button className="lv-primary lv-btn-sm" disabled={busy || !review.draft_approval || !accepted} onClick={onDraft}>{docx ? tx('导出 Word 修订版', 'Export Word') : tx('导出修订文本', 'Export revised text')}</button>
        </div>
      </div>
      <DraftRelease key={`${review.id}-${JSON.stringify(review.decisions)}`} review={review} adopted={adopted} busy={busy} onCheck={onCheck} onApprove={onApprove} onBack={onBack} />
      <p className="lv-footnote">{tx('审查结果仅供参考，不构成法律意见。', 'Review results are for reference only and are not legal advice.')}</p>
    </div>
  </section>;
}

