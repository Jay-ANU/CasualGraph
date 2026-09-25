import { ArrowUp } from 'lucide-react';
import type { Answer, Block, Review } from './types';
import { clauseLabel } from './text';
import { RichText, Spinner } from './ui';
import { ic } from './icon';

const SUGGESTED = ['哪些条款应优先谈判？', '合同缺少哪些保障条款？'];

export function FollowUp({ review, blocks, answers, question, busy, consent, onQuestion, onConsent, onAsk, onLocate }: {
  review: Review; blocks: Block[]; answers: Answer[]; question: string; busy: boolean; consent: boolean;
  onQuestion: (value: string) => void; onConsent: (value: boolean) => void; onAsk: () => void; onLocate: (id: string) => void;
}) {
  return <section className="lv-qa" aria-labelledby="legal-qa-title">
    <div className="lv-section-head"><h2 id="legal-qa-title">合同问答</h2></div>
    {answers.length > 0 && <ol className="lv-qa-log">{answers.map(a => <li key={a.id}>
      <p className="lv-qa-q">{a.question}</p>
      <div className="lv-qa-a">
        <p>{a.answer || (a.status === 'failed' ? '回答失败，请重试。' : '处理中，请稍后刷新。')}</p>
        {((a.block_refs?.length || 0) > 0 || (a.citations?.length || 0) > 0) && <div className="lv-qa-refs">
          {a.block_refs?.map((ref, i) => <button key={i} className="lv-reference" onClick={() => onLocate(ref.block_id)}><RichText text={clauseLabel(blocks.find(b => b.id === ref.block_id)) || `第 ${ref.block_id} 段`} /></button>)}
          {a.citations?.map((ref, i) => { const source = review.sources.find(x => x.id === ref.source_id); return source ? <a key={i} className="lv-reference" href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> : null; })}
        </div>}
        {a.uncertain && <small className="lv-qa-uncertain">依据不足，建议人工核实。</small>}
      </div>
    </li>)}</ol>}
    {!answers.length && <div className="lv-qa-suggest">{SUGGESTED.map(q => <button key={q} type="button" onClick={() => onQuestion(q)}>{q}</button>)}</div>}
    <div className="lv-composer">
      <textarea aria-label="追问本轮审查" maxLength={1500} rows={1} value={question} disabled={busy} onChange={e => onQuestion(e.target.value)} placeholder="就本合同提问" />
      <button className="lv-send" aria-label="发送追问" disabled={busy || !question.trim() || !consent} onClick={onAsk}>{busy ? <Spinner /> : <ArrowUp {...ic} size={18} />}</button>
    </div>
    <label className="lv-check lv-check-sm"><input type="checkbox" checked={consent} onChange={e => onConsent(e.target.checked)} /><span>同意将问题及脱敏材料提交原审查模型</span></label>
  </section>;
}
