import React, { useEffect, useRef } from 'react';

interface Piece {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  rotation: number;
  spin: number;
  colour: string;
  round: boolean;
}

const COLOURS = ['#22d3ee', '#67e8f9', '#6366f1', '#a5b4fc', '#a855f7', '#f0abfc', '#ffffff'];
const DURATION_MS = 4200;

/** A one-off burst of confetti in the brand colours, fired when `burst` changes to a new value. */
const Celebration: React.FC<{ burst: number }> = ({ burst }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!burst) return undefined;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);

    const pieces: Piece[] = [];
    [0.18, 0.5, 0.82].forEach((origin) => {
      for (let i = 0; i < 70; i += 1) {
        const angle = -Math.PI / 2 + (Math.random() - 0.5) * 1.3;
        const speed = 9 + Math.random() * 9;
        pieces.push({
          x: width * origin,
          y: height * 0.72,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          size: 5 + Math.random() * 6,
          rotation: Math.random() * Math.PI,
          spin: (Math.random() - 0.5) * 0.3,
          colour: COLOURS[Math.floor(Math.random() * COLOURS.length)],
          round: Math.random() < 0.3,
        });
      }
    });

    let frame = 0;
    const started = performance.now();
    const tick = (now: number) => {
      const elapsed = now - started;
      context.clearRect(0, 0, width, height);
      context.globalAlpha = Math.max(0, 1 - Math.max(0, elapsed - DURATION_MS * 0.6) / (DURATION_MS * 0.4));
      pieces.forEach((piece) => {
        piece.vy += 0.24;
        piece.vx *= 0.99;
        piece.vy *= 0.99;
        piece.x += piece.vx;
        piece.y += piece.vy;
        piece.rotation += piece.spin;
        context.save();
        context.translate(piece.x, piece.y);
        context.rotate(piece.rotation);
        context.fillStyle = piece.colour;
        if (piece.round) {
          context.beginPath();
          context.arc(0, 0, piece.size / 2.4, 0, Math.PI * 2);
          context.fill();
        } else {
          context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2);
        }
        context.restore();
      });
      if (elapsed < DURATION_MS) frame = window.requestAnimationFrame(tick);
      else context.clearRect(0, 0, width, height);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [burst]);

  return <canvas ref={canvasRef} className="ox-confetti" aria-hidden="true" />;
};

export default Celebration;
