import { useEffect, useRef, useState } from 'react';

const REDUCED = '(prefers-reduced-motion: reduce)';

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(REDUCED).matches;

/** Follows the system "reduce motion" setting live. */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(REDUCED);
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return reduced;
}

/** True while (or once, with `once`) the element is in the viewport. */
export function useInView<T extends Element>({ threshold = 0.2, rootMargin = '0px', once = true } = {}) {
  const ref = useRef<T>(null);
  // Without IntersectionObserver everything simply counts as visible.
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        if (once) observer.disconnect();
      } else if (!once) setInView(false);
    }, { threshold, rootMargin });
    observer.observe(element);
    return () => observer.disconnect();
  }, [threshold, rootMargin, once]);
  return [ref, inView] as const;
}

/**
 * Fades and lifts every `[data-reveal]` element inside the root the first time it scrolls into
 * view. `key` re-scans after content changes (e.g. the language), so new nodes are revealed too.
 */
export function useReveal(root: React.RefObject<HTMLElement | null>, key?: unknown) {
  useEffect(() => {
    const container = root.current;
    if (!container) return;
    const targets = Array.from(container.querySelectorAll<HTMLElement>('[data-reveal]'));
    if (typeof IntersectionObserver === 'undefined' || prefersReducedMotion()) {
      targets.forEach(el => el.classList.add('is-in'));
      return;
    }
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
    targets.filter(el => !el.classList.contains('is-in')).forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, [root, key]);
}

/**
 * Calls `onFrame` with the element's scroll progress (0 when its top reaches the viewport top,
 * 1 when its bottom reaches the viewport bottom) on every animation frame while it is near view.
 */
export function useScrollProgress(target: React.RefObject<HTMLElement | null>, onFrame: (progress: number, rect: DOMRect) => void) {
  const callback = useRef(onFrame);
  useEffect(() => { callback.current = onFrame; });
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const element = target.current;
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const span = rect.height - window.innerHeight;
      const progress = span > 0 ? Math.min(1, Math.max(0, -rect.top / span)) : rect.top <= 0 ? 1 : 0;
      callback.current(progress, rect);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [target]);
}
