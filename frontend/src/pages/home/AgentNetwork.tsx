import { useEffect, useMemo, useState } from 'react';
import { BadgeCheck, Building2, FileText, GitMerge, Landmark, Scale } from 'lucide-react';
import type { AgentCopy } from './copy';
import { useInView } from './motion';

const ICONS = { legal: Scale, commercial: Building2, policy: Landmark, critic: BadgeCheck, arbiter: GitMerge } as const;
const SIZE = 520, C = SIZE / 2, R = 188;

type Node = AgentCopy & { x: number; y: number; path: string };

/**
 * Five agents around the contract. One agent "reports" at a time: its link carries light into
 * the contract, its row lights up and a line is added to the feed. Purely illustrative.
 */
export default function AgentNetwork({ agents, feed, center, feedTitle, caption, still }: {
  agents: AgentCopy[]; feed: string[]; center: string; feedTitle: string; caption: string; still: boolean;
}) {
  const [ref, inView] = useInView<HTMLDivElement>({ threshold: 0.25, once: false });
  const [tick, setTick] = useState(0);
  const running = inView && !still;

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setTick(t => t + 1), 2400);
    return () => window.clearInterval(timer);
  }, [running]);

  const nodes: Node[] = useMemo(() => agents.map((agent, i) => {
    const angle = (-90 + i * 72) * Math.PI / 180;
    const x = C + Math.cos(angle) * R, y = C + Math.sin(angle) * R;
    // bow every link a little so the light travels on a curve
    const mx = (x + C) / 2 + Math.cos(angle + Math.PI / 2) * 34, my = (y + C) / 2 + Math.sin(angle + Math.PI / 2) * 34;
    return { ...agent, x, y, path: `M ${x.toFixed(1)} ${y.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${C} ${C}` };
  }), [agents]);

  const active = tick % agents.length;
  const lines = Array.from({ length: Math.min(feed.length, 4) }, (_, k) => {
    const n = tick - k;
    if (n < 0) return null;
    const index = n % feed.length;
    return { key: n, agent: agents[index % agents.length], text: feed[index], seconds: 8 + n * 7 };
  }).filter(Boolean) as { key: number; agent: AgentCopy; text: string; seconds: number }[];

  return (
    <div ref={ref} className={`lp-net ${running ? 'is-running' : ''}`}>
      <div className="lp-net-stage">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="lp-net-svg" role="img" aria-label={agents.map(a => a.name).join('、')}>
          <defs>
            <radialGradient id="lp-net-core" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(167,139,250,0.55)" />
              <stop offset="55%" stopColor="rgba(99,102,241,0.12)" />
              <stop offset="100%" stopColor="rgba(99,102,241,0)" />
            </radialGradient>
            {nodes.map(node => (
              <linearGradient key={node.id} id={`lp-link-${node.id}`} gradientUnits="userSpaceOnUse" x1={node.x} y1={node.y} x2={C} y2={C}>
                <stop offset="0%" className={`lp-stop-${node.tone}`} />
                <stop offset="100%" stopColor="rgba(255,255,255,0.65)" />
              </linearGradient>
            ))}
          </defs>
          <circle cx={C} cy={C} r={150} fill="url(#lp-net-core)" />
          <polygon className="lp-net-ring" points={nodes.map(n => `${n.x.toFixed(1)},${n.y.toFixed(1)}`).join(' ')} />
          {nodes.map((node, i) => (
            <g key={node.id} className={`lp-net-link ${i === active ? 'is-active' : ''}`}>
              <path d={node.path} stroke={`url(#lp-link-${node.id})`} className="lp-net-wire" />
              <path d={node.path} stroke={`url(#lp-link-${node.id})`} className="lp-net-flow" />
              {!still && (
                <circle r={i === active ? 4.5 : 2.6} className={`lp-net-pulse lp-tone-${node.tone}`}>
                  <animateMotion dur={i === active ? '1.2s' : '2.6s'} repeatCount="indefinite" path={node.path} begin={`${i * 0.37}s`} />
                </circle>
              )}
            </g>
          ))}
          <g className="lp-net-center" key={`ripple-${tick}`}>
            {!still && <circle cx={C} cy={C} r={46} className="lp-net-ripple" />}
          </g>
          <circle cx={C} cy={C} r={46} className="lp-net-core-ring" />
          <foreignObject x={C - 60} y={C - 46} width={120} height={92}>
            <div className="lp-net-doc">
              <FileText size={26} strokeWidth={1.5} aria-hidden="true" />
              <span>{center}</span>
            </div>
          </foreignObject>
          {nodes.map((node, i) => {
            const Icon = ICONS[node.id as keyof typeof ICONS] ?? Scale;
            return (
              <g key={node.id} className={`lp-net-node lp-tone-${node.tone} ${i === active ? 'is-active' : ''}`} transform={`translate(${node.x} ${node.y})`}>
                <circle r={31} className="lp-net-halo" />
                <circle r={25} className="lp-net-disc" />
                <Icon x={-11} y={-11} width={22} height={22} strokeWidth={1.6} aria-hidden="true" />
                <text y={node.y > C + 10 ? 50 : -42} textAnchor="middle" className="lp-net-label">{node.name}</text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="lp-net-side">
        <ul className="lp-net-list">
          {nodes.map((node, i) => {
            const Icon = ICONS[node.id as keyof typeof ICONS] ?? Scale;
            return (
              <li key={node.id} className={`lp-tone-${node.tone} ${i === active ? 'is-active' : ''}`}>
                <span className="lp-net-list-icon"><Icon size={17} strokeWidth={1.7} aria-hidden="true" /></span>
                <div>
                  <strong>{node.name}</strong>
                  <p>{node.role}</p>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="lp-feed" aria-hidden="true">
          <div className="lp-feed-head"><span className="lp-feed-dot" />{feedTitle}</div>
          <ol>
            {lines.map(line => (
              <li key={line.key} className={`lp-tone-${line.agent.tone}`}>
                <time>{`00:${String(line.seconds % 60).padStart(2, '0')}`}</time>
                <b>{line.agent.name}</b>
                <span>{line.text}</span>
              </li>
            ))}
          </ol>
        </div>
        <p className="lp-net-caption">{caption}</p>
      </div>
    </div>
  );
}
