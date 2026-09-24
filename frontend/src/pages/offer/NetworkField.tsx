import React, { useEffect, useRef } from 'react';

interface FieldNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  phase: number;
}

interface Pulse {
  from: number;
  to: number;
  t: number;
  speed: number;
}

const STOPS = [
  [34, 211, 238],
  [99, 102, 241],
  [168, 85, 247],
];
const SPRITE_STEPS = 12;
const SPRITE_SIZE = 64;

// Cyan on the left, indigo in the middle, violet on the right.
const colourAt = (t: number) => {
  const clamped = Math.min(1, Math.max(0, t));
  const [from, to, local] =
    clamped < 0.5 ? [STOPS[0], STOPS[1], clamped / 0.5] : [STOPS[1], STOPS[2], (clamped - 0.5) / 0.5];
  return from.map((channel, index) => Math.round(channel + (to[index] - channel) * local));
};

const makeGlowSprites = () =>
  Array.from({ length: SPRITE_STEPS }, (_, step) => {
    const sprite = document.createElement('canvas');
    sprite.width = SPRITE_SIZE;
    sprite.height = SPRITE_SIZE;
    const context = sprite.getContext('2d');
    if (context) {
      const [r, g, b] = colourAt(step / (SPRITE_STEPS - 1));
      const half = SPRITE_SIZE / 2;
      const gradient = context.createRadialGradient(half, half, 0, half, half, half);
      gradient.addColorStop(0, `rgba(${r},${g},${b},0.95)`);
      gradient.addColorStop(0.25, `rgba(${r},${g},${b},0.45)`);
      gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
      context.fillStyle = gradient;
      context.fillRect(0, 0, SPRITE_SIZE, SPRITE_SIZE);
    }
    return sprite;
  });

/**
 * Full-screen animated causal graph: drifting nodes, links that appear when nodes
 * come close, and pulses of light travelling along the links. Follows the pointer.
 */
const NetworkField: React.FC<{ className?: string }> = ({ className = '' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    const reduceMotion = Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const sprites = makeGlowSprites();
    const pointer = { x: -9999, y: -9999 };
    let width = 0;
    let height = 0;
    let nodes: FieldNode[] = [];
    let pulses: Pulse[] = [];
    let frame = 0;
    let last = 0;

    const glow = (x: number, y: number, size: number, alpha: number) => {
      const sprite = sprites[Math.min(SPRITE_STEPS - 1, Math.max(0, Math.round((x / width) * (SPRITE_STEPS - 1))))];
      context.globalAlpha = alpha;
      context.drawImage(sprite, x - size / 2, y - size / 2, size, size);
      context.globalAlpha = 1;
    };

    const seed = () => {
      const count = Math.round(Math.min(95, Math.max(28, (width * height) / 15000)));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: 0.8 + Math.random() * 1.5,
        phase: Math.random() * Math.PI * 2,
      }));
      pulses = [];
    };

    const draw = (time: number, step: number) => {
      context.clearRect(0, 0, width, height);
      const linkDistance = Math.min(170, Math.max(110, width / 9));

      if (step) {
        nodes.forEach((node) => {
          const dx = pointer.x - node.x;
          const dy = pointer.y - node.y;
          const distanceSq = dx * dx + dy * dy;
          if (distanceSq < 180 * 180 && distanceSq > 1) {
            node.vx += dx * 0.00005 * step;
            node.vy += dy * 0.00005 * step;
          }
          const speed = Math.hypot(node.vx, node.vy);
          if (speed > 0.45) {
            node.vx *= 0.45 / speed;
            node.vy *= 0.45 / speed;
          }
          node.x += node.vx * step;
          node.y += node.vy * step;
          if (node.x < -20) node.x = width + 20;
          if (node.x > width + 20) node.x = -20;
          if (node.y < -20) node.y = height + 20;
          if (node.y > height + 20) node.y = -20;
        });
      }

      context.globalCompositeOperation = 'lighter';
      context.lineWidth = 0.7;
      const strongLinks: Array<[number, number]> = [];
      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          const distance = Math.hypot(a.x - b.x, a.y - b.y);
          if (distance >= linkDistance) continue;
          const alpha = (1 - distance / linkDistance) * 0.42;
          const [r, g, bl] = colourAt((a.x + b.x) / 2 / width);
          context.strokeStyle = `rgba(${r},${g},${bl},${alpha})`;
          context.beginPath();
          context.moveTo(a.x, a.y);
          context.lineTo(b.x, b.y);
          context.stroke();
          if (alpha > 0.16) strongLinks.push([i, j]);
        }
      }

      nodes.forEach((node) => {
        const distance = Math.hypot(node.x - pointer.x, node.y - pointer.y);
        if (distance < 200) {
          context.strokeStyle = `rgba(165,180,252,${(1 - distance / 200) * 0.5})`;
          context.beginPath();
          context.moveTo(pointer.x, pointer.y);
          context.lineTo(node.x, node.y);
          context.stroke();
        }
      });

      if (step && strongLinks.length && pulses.length < 16 && Math.random() < 0.07 * step) {
        const [from, to] = strongLinks[Math.floor(Math.random() * strongLinks.length)];
        pulses.push({ from, to, t: 0, speed: 0.01 + Math.random() * 0.012 });
      }
      pulses = pulses.filter((pulse) => pulse.t <= 1 && nodes[pulse.from] && nodes[pulse.to]);
      pulses.forEach((pulse) => {
        pulse.t += pulse.speed * step;
        const a = nodes[pulse.from];
        const b = nodes[pulse.to];
        glow(a.x + (b.x - a.x) * pulse.t, a.y + (b.y - a.y) * pulse.t, 22, 1);
      });

      nodes.forEach((node) => {
        const twinkle = 0.55 + 0.45 * Math.sin(time / 900 + node.phase);
        glow(node.x, node.y, 12 + node.r * 5, twinkle * 0.85);
      });
      context.globalCompositeOperation = 'source-over';
      context.fillStyle = 'rgba(236, 254, 255, 0.9)';
      nodes.forEach((node) => {
        context.beginPath();
        context.arc(node.x, node.y, node.r, 0, Math.PI * 2);
        context.fill();
      });
    };

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      draw(0, 0);
    };

    const tick = (time: number) => {
      const step = last ? Math.min(3, (time - last) / 16.67) : 1;
      last = time;
      draw(time, step);
      frame = window.requestAnimationFrame(tick);
    };

    const onPointerMove = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
    };
    const onPointerLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };

    resize();
    window.addEventListener('resize', resize);
    if (!reduceMotion) {
      window.addEventListener('pointermove', onPointerMove);
      document.documentElement.addEventListener('pointerleave', onPointerLeave);
      frame = window.requestAnimationFrame(tick);
    }
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
      document.documentElement.removeEventListener('pointerleave', onPointerLeave);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
};

export default NetworkField;
