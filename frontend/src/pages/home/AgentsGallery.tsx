import { useEffect, useRef, useState } from 'react';
import { BadgeCheck, Building2, ChevronLeft, ChevronRight, GitMerge, Landmark, Scale } from 'lucide-react';
import type { AgentCopy } from './copy';

const ICONS = [Scale, Building2, Landmark, BadgeCheck, GitMerge];

/** A row of cards that scrolls sideways and snaps, with arrows for the pointer and keyboard. */
export default function AgentsGallery({ agents, caption, prev, next }: { agents: AgentCopy[]; caption: string; prev: string; next: string }) {
  const track = useRef<HTMLUListElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const update = () => setEdge({
      start: element.scrollLeft <= 4,
      end: element.scrollLeft + element.clientWidth >= element.scrollWidth - 4,
    });
    update();
    element.addEventListener('scroll', update, { passive: true });
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    observer?.observe(element);
    return () => { element.removeEventListener('scroll', update); observer?.disconnect(); };
  }, []);

  const step = (direction: 1 | -1) => {
    const element = track.current;
    if (!element) return;
    const card = element.querySelector<HTMLElement>('li');
    const width = card ? card.offsetWidth + 20 : element.clientWidth * 0.8;
    element.scrollBy({ left: direction * width, behavior: 'smooth' });
  };

  return (
    <div className="ap-gallery">
      <ul ref={track} className="ap-gallery-track">
        {agents.map((agent, i) => {
          const Icon = ICONS[i] ?? Scale;
          return (
            <li key={agent.name} className="ap-agent-card">
              <span className="ap-agent-icon"><Icon size={26} strokeWidth={1.5} aria-hidden="true" /></span>
              <h3>{agent.name}</h3>
              <p>{agent.role}</p>
              <div className="ap-agent-sample"><span className="ap-marker">{i + 1}</span><span>{agent.sample}</span></div>
            </li>
          );
        })}
      </ul>
      <div className="ap-gallery-foot">
        <p className="ap-caption">{caption}</p>
        <div className="ap-gallery-nav">
          <button type="button" onClick={() => step(-1)} disabled={edge.start} aria-label={prev}><ChevronLeft size={18} strokeWidth={2.2} aria-hidden="true" /></button>
          <button type="button" onClick={() => step(1)} disabled={edge.end} aria-label={next}><ChevronRight size={18} strokeWidth={2.2} aria-hidden="true" /></button>
        </div>
      </div>
    </div>
  );
}
