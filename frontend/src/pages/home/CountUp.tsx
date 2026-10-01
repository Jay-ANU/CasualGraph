import { useEffect } from 'react';
import { useInView } from './motion';

/** Counts from zero to `value` (ease-out) the first time it scrolls into view. */
export default function CountUp({ value, still }: { value: number; still: boolean }) {
  const [ref, inView] = useInView<HTMLSpanElement>({ threshold: 0.6 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (still) { element.textContent = String(value); return; }
    if (!inView) { element.textContent = '0'; return; }
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const t = Math.min(1, (now - start) / 1400);
      element.textContent = String(t >= 1 ? value : Math.round(value * (1 - Math.pow(2, -10 * t))));
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [ref, inView, value, still]);

  return <span ref={ref} className="lp-count">{value}</span>;
}
