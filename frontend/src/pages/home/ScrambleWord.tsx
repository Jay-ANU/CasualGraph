import { useEffect, useRef, useState } from 'react';

const GLYPHS = {
  zh: '合同条款审查风险依据修订脱敏责任违约付款交付验收保密许可期限争议管辖解除赔偿',
  en: 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&+=/<>',
};

/**
 * Cycles through `words`, decoding each one from random glyphs like a terminal resolving a
 * value. Frames are written straight to the DOM; React only tracks which word is current.
 * Remount it (via `key`) when the word list changes language.
 */
export default function ScrambleWord({ words, lang, still, interval = 2800 }: {
  words: string[]; lang: 'zh' | 'en'; still: boolean; interval?: number;
}) {
  const [index, setIndex] = useState(0);
  const node = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (still || words.length < 2) return;
    const timer = window.setInterval(() => setIndex(i => (i + 1) % words.length), interval);
    return () => window.clearInterval(timer);
  }, [still, words.length, interval]);

  useEffect(() => {
    const element = node.current;
    const target = words[index] ?? '';
    if (!element) return;
    if (still) { element.textContent = target; return; }
    const glyphs = GLYPHS[lang];
    const steps = 14 + target.length * 2;
    let step = 0;
    let timer = 0;
    const tick = () => {
      step += 1;
      const settled = Math.floor((step / steps) * target.length);
      let out = '';
      for (let i = 0; i < target.length; i++) {
        out += i < settled || target[i] === ' ' ? target[i] : glyphs[Math.floor(Math.random() * glyphs.length)];
      }
      element.textContent = out;
      if (settled < target.length) timer = window.setTimeout(tick, 32);
    };
    timer = window.setTimeout(tick, 0);
    return () => window.clearTimeout(timer);
  }, [index, words, lang, still]);

  return <span ref={node} className="lp-scramble" aria-hidden="true">{words[0]}</span>;
}
