import { useState } from 'react';
import { FileDown, FileText } from 'lucide-react';
import type { Contract, Review } from './types';
import type { Numbered } from './workspace';
import type { RevisionFormat } from './exportFlow';
import { isRevised } from './workspace';
import { pendingDecisions } from './deskLogic';
import { Marker } from './Marker';
import { Spinner } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { plural, serverText } from './i18n';
import { processingConsent, processingProvider, reviewRouteKey } from './modelProcessing';

/** A second model opinion is available on request and never controls export. */
function OptionalCheck({ review, selected, busy, onCheck }: { review: Review; selected: boolean; busy: boolean; onCheck: () => void }) {
  const { tx, lang } = useI18n();
  const [externalConsent, setExternalConsent] = useState(false);
  const checked = review.draft_check;
  const provider = processingProvider(review.profile?.model);
  return <details className="lv-disclosure">
    <summary>{tx('可选：复核当前修订稿', 'Optional: check this revision')}</summary>
    <div className="lv-disclosure-body">
      <p>{tx('需要第二遍模型意见时再运行；复核结果供你参考。', 'Run a second model review when you want another opinion.')}</p>
      <label className="lv-check lv-check-sm"><input type="checkbox" checked={externalConsent && Boolean(provider)} disabled={busy || !selected || !provider} onChange={e => setExternalConsent(e.target.checked)} />
        <span>{processingConsent('check', provider, lang)}</span></label>
      <button className="lv-secondary lv-btn-sm" disabled={busy || !externalConsent || !selected || !provider} onClick={onCheck}>{busy && <Spinner />}{tx('开始复核', 'Run optional check')}</button>
      {checked && <div className={`lv-check-result ${checked.status === 'verified' ? 'is-ok' : 'is-warn'}`} role="status">
        <strong>{checked.status === 'verified' ? tx('模型复核未发现冲突', 'The model found no conflicts') : tx('模型复核提示', 'Model review notes')}</strong>
        <p>{serverText(checked.whole_contract.reason)}</p>
        {checked.checks.filter(item => item.status !== 'supported').map(item => <p key={item.finding_id}>{serverText(item.reason)}</p>)}
        {checked.missing_facts.map((item, i) => <p key={i}>{serverText(item)}</p>)}
      </div>}
    </div>
  </details>;
}

export function ReleasePanel({ review, contract, open, busy, onCheck, onReport, onDraft, onBack }: {
  review: Review; contract: Contract; open: Numbered[]; busy: boolean;
  onCheck: () => void; onReport: () => void; onDraft: (format: RevisionFormat) => void; onBack: () => void;
}) {
  const { tx } = useI18n();
  const docx = contract.format === 'docx';
  const pdf = contract.format === 'pdf';
  const adopted = open.filter(x => isRevised(review.decisions[x.finding.id]));
  const pending = review.export_state?.pending_count ?? pendingDecisions(review);
  return <section id="legal-release" className="lv-rail-panel" aria-labelledby="legal-release-title">
    <div className="lv-rail-head">
      <h2 id="legal-release-title">{tx('导出', 'Export')}</h2>
      <p>{tx('查看当前修订稿后即可导出。有待处理项时，确认一次即可继续。', 'Export after reading the current draft. If items are pending, confirm once to continue.')}</p>
    </div>
    <div className="lv-rail-body">
      <div className="lv-export-summary">
        <strong>{tx(`已写入 ${adopted.length} 项修改`, `${plural(adopted.length, 'edit')} in the current draft`)}</strong>
        <p role="status">{pending > 0 ? tx(`还有 ${pending} 项待处理，可继续导出当前稿。`, `${plural(pending, 'item')} pending. You can still export this draft.`)
          : tx('没有待处理项，点击即可下载。', 'No pending items. Download in one click.')}</p>
        {(review.export_state?.appendix_count || 0) > 0 && <p>{tx(`${review.export_state!.appendix_count} 项修改将列入附录，原件对应内容保留。`,
          `${plural(review.export_state!.appendix_count!, 'edit')} will appear in the appendix; the corresponding original content is retained.`)}</p>}
        <div className="lv-release-marks">{adopted.map(x => <Marker key={x.finding.id} n={x.n} finding={x.finding} state="revised" size="sm" number />)}
          <button className="lv-text-button" onClick={onBack}>{tx('查看与编辑修订稿', 'Read and edit the draft')}</button></div>
      </div>
      <div className="lv-export-list">
        <div className="lv-export-row">
          <span className="lv-tile is-gray"><FileDown {...ic} size={18} /></span>
          <div><strong>{docx ? tx('Word 修订版', 'Tracked-changes Word') : pdf ? tx('带批注原 PDF', 'Annotated original PDF') : tx('修订文本', 'Revised text')}</strong>
            <span>{docx ? tx('原文件中保留修订痕迹；无法直接改写的内容列入附录 · DOCX', 'Tracked changes in the original; edits to read-only content are listed in an appendix · DOCX')
              : pdf ? tx('原页不变，修改列入批注和附录 · PDF', 'Original pages retained; edits appear in comments and an appendix · PDF')
                : tx('纯文本，不含修订痕迹 · TXT', 'Plain text without tracked changes · TXT')}</span></div>
          <button className="lv-primary lv-btn-sm" disabled={busy} onClick={() => onDraft(docx ? 'docx' : pdf ? 'pdf' : 'txt')}>{docx ? tx('导出 Word 修订版', 'Export Word')
            : pdf ? tx('导出带批注 PDF', 'Export annotated PDF') : tx('导出修订文本', 'Export revised text')}</button>
        </div>
        {(docx || pdf) && <div className="lv-export-row">
          <span className="lv-tile is-gray"><FileText {...ic} size={18} /></span>
          <div><strong>{tx('文字稿', 'Text version')}</strong><span>{tx('不保留原排版和修订痕迹 · TXT', 'Without original layout or tracked changes · TXT')}</span></div>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={() => onDraft('txt')}>{tx('导出文字稿', 'Export text')}</button>
        </div>}
        <div className="lv-export-row">
          <span className="lv-tile is-gray"><FileText {...ic} size={18} /></span>
          <div><strong>{tx('审查报告', 'Review report')}</strong><span>{tx('意见、依据及处理结果 · Markdown', 'Findings, basis and decisions · Markdown')}</span></div>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onReport}>{tx('导出报告', 'Export report')}</button>
        </div>
      </div>
      <OptionalCheck key={`${review.id}-${reviewRouteKey(review)}-${JSON.stringify(review.decisions)}`} review={review} selected={adopted.length > 0} busy={busy} onCheck={onCheck} />
      <p className="lv-footnote">{tx('导出文件包含未脱敏信息；Word 修订版还会保留删除内容，请按需要分享。', 'Exports contain unredacted information; Word revisions also retain deleted text. Share accordingly.')}</p>
    </div>
  </section>;
}
