import { useState } from 'react';
import type { Block, Review } from './types';

export function PartyBinding({ blocks, blockId, quote, disabled, onChange }: {
  blocks: Block[]; blockId: string; quote: string; disabled: boolean;
  onChange: (blockId: string, quote: string) => void;
}) {
  const selected = blocks.find(b => b.id === blockId);
  const valid = quote.trim().length >= 2 && !!selected?.text.includes(quote);
  return <fieldset className="lv-party-binding" disabled={disabled}>
    <legend>我方对应合同中的哪一个主体？</legend>
    <p className="lv-muted">角色不等于主体。请从脱敏正文选择一段，并逐字填写能识别我方的片段，例如「乙方【脱敏2】」。多方合同不要只填共同角色。</p>
    <label>主体所在段落<select aria-label="我方主体所在段落" value={blockId} onChange={e => onChange(e.target.value, '')}>
      <option value="">选择原文段落</option>{blocks.map(b => <option key={b.id} value={b.id}>{b.id} · {b.text.slice(0, 65)}</option>)}
    </select></label>
    {selected && <blockquote>{selected.text}</blockquote>}
    <label>我方主体原文<input aria-label="我方主体原文" maxLength={200} value={quote} onChange={e => onChange(blockId, e.target.value)} placeholder="从所选段落逐字填写" /></label>
    {quote && !valid && <p className="lv-inline-warning">未匹配所选段落，不能使用猜测或其他版本的主体信息。</p>}
  </fieldset>;
}

export function DraftReleasePanel({ review, busy, onCheck, onApprove }: {
  review: Review; busy: boolean; onCheck: () => void; onApprove: (fingerprint: string) => void;
}) {
  const [externalConsent, setExternalConsent] = useState(false);
  const [humanConsent, setHumanConsent] = useState(false);
  const selected = Object.values(review.decisions).filter(d => ['accepted', 'draft'].includes(d.decision));
  const drafts = selected.filter(d => d.decision === 'draft').length;
  const checked = review.draft_check;
  return <section className="lv-step-card" aria-label="最终修订组合核验">
    <h2>导出前，检查实际选中的修改</h2>
    <p>{selected.length} 项已选修改，其中 {drafts} 项是待复核的手工草稿。只复核实际组合，不把未采纳建议当作已修改。</p>
    {review.draft_approval ? <p role="status">当前修订组合已由用户确认。后续任何决定变化都会使此确认失效；这不代表企业授权审批或签署已完成。</p> : <>
      <label className="lv-consent"><input type="checkbox" checked={externalConsent} disabled={busy} onChange={e => setExternalConsent(e.target.checked)} />允许将当前脱敏修订组合交给原审查模型复核。</label>
      <button className="lv-secondary" disabled={busy || !externalConsent || !selected.length} onClick={onCheck}>核验所选修订</button>
      {checked && <div className="lv-draft-check" role="status">
        <strong>{checked.status === 'verified' ? '模型组合核验完成，仍需人工确认' : '组合核验未通过，暂不能导出修订稿'}</strong>
        <p>{checked.whole_contract.reason}</p>
        {checked.checks.map(item => <p key={item.finding_id}>{item.status === 'supported' ? '已比较' : '待处理'}：{item.reason}</p>)}
        {checked.missing_facts.map((item, i) => <p key={i} className="lv-inline-warning">{item}</p>)}
      </div>}
      {checked?.status === 'verified' && <>
        <label className="lv-consent"><input type="checkbox" checked={humanConsent} disabled={busy} onChange={e => setHumanConsent(e.target.checked)} />我已核对当前完整修改组合、法律适用及剩余风险，确认生成这份修订稿。</label>
        <button className="lv-primary" disabled={busy || !humanConsent} onClick={() => onApprove(checked.fingerprint)}>确认当前修订组合</button>
      </>}
    </>}
    <small>审查报告始终可以单独导出。修订稿含真实信息和删除内容，不是脱敏副本，也不是可直接签署的自动批准稿。</small>
  </section>;
}
