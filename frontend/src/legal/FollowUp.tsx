import { ArrowUp } from 'lucide-react';
import type { Answer, Block, Review } from './types';
import { clauseLabel } from './text';
import { RichText, Spinner } from './ui';
import { ic } from './icon';

const SUGGESTED = ['最需要优先谈的是哪几条？', '这份合同还缺少什么保障？'];

export function FollowUp({ review, blocks, answers, question, busy, consent, onQuestion, onConsent, onAsk, onLocate }: {
  review: Review; blocks: Block[]; answers: Answer[]; question: string; busy: boolean; consent: boolean;
  onQuestion: (value: string) => void; onConsent: (value: boolean) => void; onAsk: () => void; onLocate: (id: string) => void;
}) {
  return <section className="lv-qa" aria-labelledby="legal-qa-title">
    <div className="lv-section-head"><h2 id="legal-qa-title">对这份合同还有疑问？</h2></div>
    <p className="lv-hint">回答基于本轮审查的模型和已取得的依据，只做解释，不会修改合同。</p>
    {answers.length > 0 && <ol className="lv-qa-log">{answers.map(a => <li key={a.id}>
      <p className="lv-qa-q">{a.question}</p>
      <div className="lv-qa-a">
        <p>{a.answer || (a.status === 'failed' ? '这个问题没有回答成功，请重新发送。' : '正在处理，请稍后刷新查看。')}</p>
        {((a.block_refs?.length || 0) > 0 || (a.citations?.length || 0) > 0) && <div className="lv-qa-refs">
          {a.block_refs?.map((ref, i) => <button key={i} className="lv-reference" onClick={() => onLocate(ref.block_id)}><RichText text={clauseLabel(blocks.find(b => b.id === ref.block_id)) || `第 ${ref.block_id} 段`} /></button>)}
          {a.citations?.map((ref, i) => { const source = review.sources.find(x => x.id === ref.source_id); return source ? <a key={i} className="lv-reference" href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> : null; })}
        </div>}
        {a.uncertain && <small className="lv-qa-uncertain">依据仍不充分，这一点需要人工核实。</small>}
      </div>
    </li>)}</ol>}
    <div className="lv-qa-suggest">{SUGGESTED.map(q => <button key={q} type="button" onClick={() => onQuestion(q)}>{q}</button>)}</div>
    <div className="lv-composer">
      <textarea aria-label="追问本轮审查" maxLength={1500} rows={2} value={question} disabled={busy} onChange={e => onQuestion(e.target.value)} placeholder="例如：第五条的违约金为什么对我不利？" />
      <button className="lv-send" aria-label="发送追问" disabled={busy || !question.trim() || !consent} onClick={onAsk}>{busy ? <Spinner /> : <ArrowUp {...ic} size={18} />}</button>
    </div>
    <label className="lv-check"><input type="checkbox" checked={consent} onChange={e => onConsent(e.target.checked)} /><span>允许将本次提问及本轮脱敏材料发送给原审查模型。</span></label>
  </section>;
}
