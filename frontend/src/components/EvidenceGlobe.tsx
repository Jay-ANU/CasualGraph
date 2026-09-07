import React, { useEffect, useRef } from 'react';

/** Decorative, bounded canvas. No API requests, model calls, or report data. */
export default function EvidenceGlobe() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const points = Array.from({ length: 380 }, (_, i) => {
      const y = 1 - (i / 379) * 2;
      const radius = Math.sqrt(1 - y * y);
      const angle = i * Math.PI * (3 - Math.sqrt(5));
      return { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius };
    });
    let width = 0;
    let height = 0;
    let angle = 0.24;
    let frame = 0;
    let last = 0;
    let visible = false;
    let disposed = false;
    const draw = () => {
      const ctx = context;
      ctx.clearRect(0, 0, width, height);
      const radius = Math.min(width * 0.35, height * 0.43);
      const cx = width / 2;
      const cy = height / 2;
      const halo = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius * 1.45);
      halo.addColorStop(0, 'rgba(61, 92, 180, 0.06)');
      halo.addColorStop(0.58, 'rgba(87, 109, 230, 0.075)');
      halo.addColorStop(1, 'rgba(60, 100, 230, 0)');
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, width, height);
      const projected = points.map(p => {
        const x = p.x * Math.cos(angle) - p.z * Math.sin(angle);
        const z = p.x * Math.sin(angle) + p.z * Math.cos(angle);
        const y = p.y * 0.94 - z * 0.34;
        return { x: cx + x * radius, y: cy + y * radius, z };
      });
      // Constant-degree mesh instead of an O(n²) proximity search every frame.
      projected.forEach((p, i) => {
        [13, 21].forEach(offset => {
          const q = projected[(i + offset) % points.length];
          if (Math.hypot(p.x - q.x, p.y - q.y) > radius * 0.38) return;
          ctx.strokeStyle = `rgba(137, 164, 243, ${0.025 + Math.max(0, (p.z + q.z) / 2) * 0.13})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
        });
        const depth = (p.z + 1) / 2;
        ctx.fillStyle = `rgba(184, 206, 255, ${0.08 + depth * 0.72})`;
        ctx.beginPath(); ctx.arc(p.x, p.y, 0.6 + depth * 1.1, 0, Math.PI * 2); ctx.fill();
        if (i % 41 === 0 && depth > 0.45) {
          ctx.strokeStyle = `rgba(180, 203, 255, ${depth * 0.35})`;
          ctx.beginPath(); ctx.arc(p.x, p.y, 5.5, 0, Math.PI * 2); ctx.stroke();
        }
      });
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(-0.24);
      ctx.strokeStyle = 'rgba(169, 188, 245, 0.2)'; ctx.lineWidth = 0.7;
      ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.18, radius * 0.32, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    };
    const tick = (time: number) => {
      frame = 0;
      if (disposed || !visible || document.hidden || media.matches) return;
      if (time - last > 32) { angle += 0.0018; draw(); last = time; }
      frame = window.requestAnimationFrame(tick);
    };
    const schedule = () => {
      window.cancelAnimationFrame(frame); frame = 0;
      if (!disposed && visible && !document.hidden && !media.matches) frame = window.requestAnimationFrame(tick);
    };
    const resize = () => {
      const box = canvas.getBoundingClientRect();
      width = box.width; height = box.height;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0); draw();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; schedule(); });
    intersection.observe(canvas);
    media.addEventListener('change', schedule);
    document.addEventListener('visibilitychange', schedule);
    resize();
    return () => {
      disposed = true; window.cancelAnimationFrame(frame);
      observer.disconnect(); intersection.disconnect();
      media.removeEventListener('change', schedule);
      document.removeEventListener('visibilitychange', schedule);
    };
  }, []);
  return <canvas ref={canvasRef} className="research-globe" aria-hidden="true" />;
}
