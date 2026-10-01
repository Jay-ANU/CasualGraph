import { useRef } from 'react';
import { BookMarked, Cpu, EyeOff, FileDiff, Gauge, Layers, MessagesSquare, ScrollText } from 'lucide-react';
import type { CapabilityCopy } from './copy';

const ICONS = [EyeOff, Layers, Gauge, BookMarked, ScrollText, FileDiff, MessagesSquare, Cpu];
const SPANS = ['wide', '', '', '', '', 'wide', 'wide', 'wide'];

function Visual({ index, lang }: { index: number; lang: 'zh' | 'en' }) {
  switch (index) {
    case 0: return (
      <div className="lp-vis-mask" aria-hidden="true">
        {[86, 64, 92, 48].map((w, i) => <span key={i} style={{ width: `${w}%`, '--i': i } as React.CSSProperties}><i /></span>)}
      </div>
    );
    case 1: return (
      <div className="lp-vis-tags" aria-hidden="true">
        {(lang === 'zh' ? ['采购', '销售', '服务', '保密', '许可', 'SaaS', '租赁', '经销', '物流'] : ['Purchase', 'Sales', 'Services', 'NDA', 'Licence', 'SaaS', 'Lease', 'Distribution', 'Logistics'])
          .map((tag, i) => <span key={tag} style={{ '--i': i } as React.CSSProperties}>{tag}</span>)}
      </div>
    );
    case 2: return (
      <div className="lp-vis-depth" aria-hidden="true">{[28, 46, 68, 92].map((h, i) => <span key={h} style={{ height: `${h}%`, '--i': i } as React.CSSProperties} />)}</div>
    );
    case 3: return (
      <div className="lp-vis-cite" aria-hidden="true">
        <span>{lang === 'zh' ? '《民法典》第五百八十五条' : 'Civil Code, Art. 585'}</span>
        <span>{lang === 'zh' ? '官方来源 · 已核验' : 'Official source · verified'}</span>
      </div>
    );
    case 4: return (
      <ul className="lp-vis-rules" aria-hidden="true">
        {(lang === 'zh' ? ['付款须验收后支付', '违约金不超过 20%', '争议由我方所在地管辖'] : ['Pay only after acceptance', 'Damages capped at 20%', 'Disputes heard where we are'])
          .map((rule, i) => <li key={rule} style={{ '--i': i } as React.CSSProperties}><span />{rule}</li>)}
      </ul>
    );
    case 6: return (
      <div className="lp-vis-chat" aria-hidden="true">
        <span className="q">{lang === 'zh' ? '这条违约金为什么可能过高？' : 'Why might this penalty be too high?'}</span>
        <span className="a">{lang === 'zh' ? '约定为合同总价的 50%，明显高于可能的损失…' : 'It is set at 50% of the price, well above the likely loss…'}</span>
      </div>
    );
    case 5: return (
      <div className="lp-vis-word" aria-hidden="true">
        <span className="w-row"><i style={{ width: '70%' }} /></span>
        <span className="w-row"><del>{lang === 'zh' ? '签订后 5 日内' : 'within 5 days of signing'}</del><ins>{lang === 'zh' ? '验收后 30 日内' : 'within 30 days of acceptance'}</ins></span>
        <span className="w-row"><i style={{ width: '54%' }} /></span>
      </div>
    );
    case 7: return (
      <div className="lp-vis-models" aria-hidden="true">{['GPT', 'Claude', 'DeepSeek', 'Kimi', 'GLM'].map((m, i) => <span key={m} style={{ '--i': i } as React.CSSProperties}>{m}</span>)}</div>
    );
    default: return null;
  }
}

/** Bento grid; a soft light follows the pointer across the card borders (Linear-style). */
export default function Capabilities({ items, lang }: { items: CapabilityCopy[]; lang: 'zh' | 'en' }) {
  const grid = useRef<HTMLDivElement>(null);
  const onMove = (event: React.PointerEvent) => {
    grid.current?.querySelectorAll<HTMLElement>('.lp-card').forEach(card => {
      const box = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${event.clientX - box.left}px`);
      card.style.setProperty('--my', `${event.clientY - box.top}px`);
    });
  };
  return (
    <div ref={grid} className="lp-bento" onPointerMove={onMove}>
      {items.map((item, i) => {
        const Icon = ICONS[i] ?? Layers;
        return (
          // Keyed by position: a language switch must not remount (and re-hide) revealed cards.
          <article key={i} className={`lp-card ${SPANS[i] ? `is-${SPANS[i]}` : ''}`} data-reveal style={{ '--d': `${(i % 4) * 70}ms` } as React.CSSProperties}>
            <span className="lp-card-icon"><Icon size={19} strokeWidth={1.6} aria-hidden="true" /></span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
            <div className="lp-card-vis"><Visual index={i} lang={lang} /></div>
          </article>
        );
      })}
    </div>
  );
}
