import { useEffect, useRef } from 'react';

type Spark = { x: number; y: number; z: number; vx: number; vy: number; r: number; c: number; tw: number };

const COLORS = ['167,139,250', '34,211,238', '244,114,182', '147,197,253', '224,231,255'];

function sprite(rgb: string) {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const g = canvas.getContext('2d');
  if (g) {
    const gradient = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gradient.addColorStop(0, `rgba(255,255,255,1)`);
    gradient.addColorStop(0.18, `rgba(${rgb},0.9)`);
    gradient.addColorStop(0.45, `rgba(${rgb},0.25)`);
    gradient.addColorStop(1, `rgba(${rgb},0)`);
    g.fillStyle = gradient;
    g.fillRect(0, 0, size, size);
  }
  return canvas;
}

/**
 * Live layer over the hero video: luminous motes at three depths that drift upward and lean
 * toward the pointer, so the scene answers the visitor. Cheap 2D canvas, capped pixel ratio,
 * and it stops drawing whenever `active` is false.
 */
export default function SparkField({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const activeRef = useRef(active);
  const wake = useRef<() => void>(() => {});

  useEffect(() => {
    activeRef.current = active;
    if (active) wake.current();
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const sprites = COLORS.map(sprite);
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    let sparks: Spark[] = [];
    let width = 0, height = 0, ratio = 1, frame = 0, last = 0;

    const seed = () => {
      const count = Math.round(Math.min(130, Math.max(36, (width * height) / 15000)));
      sparks = Array.from({ length: count }, () => {
        const z = 0.25 + Math.random() * 0.75;
        return { x: Math.random(), y: Math.random(), z, vx: (Math.random() - 0.5) * 0.004, vy: -(0.004 + Math.random() * 0.012) * z,
          r: 2 + z * 7 * (Math.random() < 0.08 ? 2.2 : 1), c: Math.floor(Math.random() * COLORS.length), tw: Math.random() * Math.PI * 2 };
      });
    };
    const resize = () => {
      const box = canvas.getBoundingClientRect();
      ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = Math.max(1, box.width); height = Math.max(1, box.height);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (!sparks.length) seed();
    };
    const draw = (time: number) => {
      const dt = last ? Math.min(0.05, (time - last) / 1000) : 0.016;
      last = time;
      pointer.x += (pointer.tx - pointer.x) * 0.06;
      pointer.y += (pointer.ty - pointer.y) * 0.06;
      context.clearRect(0, 0, width, height);
      context.globalCompositeOperation = 'lighter';
      for (const s of sparks) {
        s.x += s.vx * dt * 6; s.y += s.vy * dt * 6;
        if (s.y < -0.05) { s.y = 1.05; s.x = Math.random(); }
        if (s.x < -0.05) s.x = 1.05; else if (s.x > 1.05) s.x = -0.05;
        const twinkle = 0.55 + 0.45 * Math.sin(time * 0.0016 + s.tw);
        const px = s.x * width + pointer.x * s.z * 34;
        const py = s.y * height + pointer.y * s.z * 22;
        const size = s.r * (0.85 + 0.3 * twinkle);
        context.globalAlpha = (0.18 + 0.5 * s.z) * twinkle;
        context.drawImage(sprites[s.c], px - size, py - size, size * 2, size * 2);
      }
      context.globalAlpha = 1;
      context.globalCompositeOperation = 'source-over';
    };
    const loop = (time: number) => {
      frame = 0;
      draw(time);
      if (activeRef.current && !document.hidden) frame = requestAnimationFrame(loop);
    };
    wake.current = () => { if (!frame) { last = 0; frame = requestAnimationFrame(loop); } };
    const onPointer = (event: PointerEvent) => {
      pointer.tx = event.clientX / window.innerWidth - 0.5;
      pointer.ty = event.clientY / window.innerHeight - 0.5;
    };
    const onVisible = () => { if (!document.hidden && activeRef.current) wake.current(); };

    resize();
    draw(performance.now());
    if (activeRef.current) wake.current();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    observer?.observe(canvas);
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      observer?.disconnect();
      window.removeEventListener('pointermove', onPointer);
      document.removeEventListener('visibilitychange', onVisible);
      if (frame) cancelAnimationFrame(frame);
      wake.current = () => {};
    };
  }, []);

  return <canvas ref={canvasRef} className="lp-sparks" aria-hidden="true" />;
}
