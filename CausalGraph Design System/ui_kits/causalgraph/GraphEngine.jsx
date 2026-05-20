/* global React, Panel, Button, IconButton, DomainTag, Pill */
const { useState, useEffect } = React;

const NODES = [
  { id: 'bhp',  label: 'BHP',                 x: 380, y: 220, domain: 'Environmental', type: 'Company' },
  { id: 'rio',  label: 'Rio Tinto',           x: 200, y: 380, domain: 'Environmental', type: 'Company' },
  { id: 'fmg',  label: 'Fortescue',           x: 580, y: 380, domain: 'Environmental', type: 'Company' },
  { id: 's1',   label: 'scope_1',             x: 380, y: 380, domain: 'General',       type: 'Metric'  },
  { id: 't30',  label: '-30% FY30',           x: 480, y: 510, domain: 'Environmental', type: 'Target'  },
  { id: 't15',  label: 'net-zero op CY2030',  x: 700, y: 510, domain: 'Environmental', type: 'Target'  },
  { id: 'ctap', label: 'CTAP 2024',           x: 230, y: 220, domain: 'Governance',    type: 'Document'},
  { id: 'cdp',  label: 'CDP A-list',          x: 530, y: 100, domain: 'Governance',    type: 'Rating'  },
];
const EDGES = [
  { a: 'bhp', b: 'ctap', label: 'PUBLISHES' },
  { a: 'bhp', b: 's1',   label: 'DISCLOSES' },
  { a: 'rio', b: 's1',   label: 'DISCLOSES' },
  { a: 'fmg', b: 's1',   label: 'DISCLOSES' },
  { a: 's1',  b: 't30',  label: 'HAS_TARGET' },
  { a: 'fmg', b: 't15',  label: 'HAS_TARGET' },
  { a: 'bhp', b: 'cdp',  label: 'RATED_AS' },
];

const RELATIONSHIPS = [
  { cause: 'BHP',       relation: 'HAS_TARGET',  effect: 'scope_1 -30% FY30',     conf: 0.92, evidence: 'bhp-2024-sustainability.pdf p.42' },
  { cause: 'Rio Tinto', relation: 'HAS_TARGET',  effect: 'scope_1 -30% FY30 (m)', conf: 0.89, evidence: 'rio-tinto-climate-report-2024.pdf p.11' },
  { cause: 'Fortescue', relation: 'HAS_TARGET',  effect: 'net-zero op CY2030',    conf: 0.95, evidence: 'fmg-cap-2024.pdf p.6' },
  { cause: 'BHP',       relation: 'RATED_AS',    effect: 'CDP A-list 2024',       conf: 0.78, evidence: 'cdp-2024-results.pdf p.3' },
];

function GraphEngine() {
  const [selected, setSelected] = useState('bhp');
  const [domains, setDomains] = useState({ Environmental: true, Social: true, Governance: true, General: true });
  const [layout, setLayout] = useState('force');

  useEffect(() => { window.lucide && window.lucide.createIcons(); }, [selected, domains, layout]);

  const visibleNodes = NODES.filter(n => domains[n.domain]);
  const visibleIds = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = EDGES.filter(e => visibleIds.has(e.a) && visibleIds.has(e.b));

  const node = NODES.find(n => n.id === selected) || NODES[0];

  return (
    <div className="grid h-[calc(100vh-72px)] grid-cols-[1fr_380px] bg-slate-50">
      <section className="flex flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white/86 backdrop-blur px-6 py-3">
          <div>
            <div className="text-base font-semibold text-slate-950">Causal Knowledge Graph</div>
            <div className="text-[12px] text-slate-500 font-mono">{visibleNodes.length} nodes · {visibleEdges.length} edges · 3 indexed reports</div>
          </div>
          <div className="flex items-center gap-2">
            {Object.keys(domains).map(d => (
              <Pill key={d} active={domains[d]} onClick={() => setDomains({...domains, [d]: !domains[d]})}>{d}</Pill>
            ))}
            <div className="ml-2 flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
              {['force','radial','grid'].map(l => (
                <button key={l} onClick={()=>setLayout(l)}
                  className={`rounded px-2.5 py-1 text-[12px] font-medium ${layout===l ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{l}</button>
              ))}
            </div>
          </div>
        </header>

        <div className="relative flex-1 overflow-hidden">
          <div className="absolute inset-0 app-grid"></div>
          <svg viewBox="0 0 880 600" className="absolute inset-0 h-full w-full">
            {visibleEdges.map((e, i) => {
              const a = NODES.find(n=>n.id===e.a), b = NODES.find(n=>n.id===e.b);
              const active = selected === e.a || selected === e.b;
              return (
                <g key={i}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active ? '#0f172a' : '#cbd5e1'} strokeWidth={active ? 2 : 1.2} />
                  <text x={(a.x+b.x)/2} y={(a.y+b.y)/2 - 6} textAnchor="middle" fontSize="10" fontFamily="IBM Plex Mono, monospace" fill={active ? '#334155' : '#94a3b8'}>{e.label}</text>
                </g>
              );
            })}
            {visibleNodes.map(n => {
              const fills = { Environmental:'#ecfdf5', Social:'#eff6ff', Governance:'#fff7ed', General:'#ffffff', AI:'#f5f3ff' };
              const strokes = { Environmental:'#047857', Social:'#1d4ed8', Governance:'#b45309', General:'#0f172a', AI:'#6d28d9' };
              const r = n.type === 'Company' ? 32 : 26;
              const isSel = selected === n.id;
              return (
                <g key={n.id} onClick={()=>setSelected(n.id)} style={{cursor:'pointer'}}>
                  {isSel && <circle cx={n.x} cy={n.y} r={r+6} fill="none" stroke="#0f172a" strokeWidth="1.5" strokeDasharray="3 3" />}
                  <circle cx={n.x} cy={n.y} r={r} fill={fills[n.domain]} stroke={strokes[n.domain]} strokeWidth="1.6" />
                  <text x={n.x} y={n.y+4} textAnchor="middle" fontSize="11" fontFamily="IBM Plex Mono, monospace" fill="#0f172a" fontWeight="600">{n.label}</text>
                </g>
              );
            })}
          </svg>
          <div className="absolute bottom-4 left-4 flex items-center gap-2">
            <IconButton icon={(p)=><i data-lucide="zoom-in" {...p}></i>} label="Zoom in" />
            <IconButton icon={(p)=><i data-lucide="zoom-out" {...p}></i>} label="Zoom out" />
            <IconButton icon={(p)=><i data-lucide="maximize-2" {...p}></i>} label="Fit" />
          </div>
        </div>
      </section>

      <aside className="flex flex-col border-l border-slate-200 bg-white/72 backdrop-blur">
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-2">Selected entity</div>
          <div className="flex items-baseline gap-2">
            <div className="text-xl font-semibold tracking-tight text-slate-950">{node.label}</div>
            <DomainTag domain={node.domain} />
          </div>
          <div className="mt-1 font-mono text-[11px] text-slate-500">{node.type} · id {node.id}</div>
        </div>
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-2">Outgoing edges · {EDGES.filter(e=>e.a===node.id).length}</div>
          {EDGES.filter(e=>e.a===node.id).map((e, i) => {
            const tgt = NODES.find(n=>n.id===e.b);
            return (
              <div key={i} className="mb-1.5 flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-[12px]">
                <span className="font-mono text-slate-500">{e.label}</span>
                <span className="font-semibold text-slate-900">{tgt.label}</span>
              </div>
            );
          })}
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-3">Relationship table</div>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left font-mono text-[10.5px] uppercase tracking-[0.1em] text-slate-500">
                <th className="pb-2">Cause → Effect</th>
                <th className="pb-2 text-right">Conf.</th>
              </tr>
            </thead>
            <tbody>
              {RELATIONSHIPS.map((r, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-2 pr-2">
                    <div className="font-medium text-slate-900">{r.cause}</div>
                    <div className="font-mono text-[10.5px] text-slate-500">{r.relation} → {r.effect}</div>
                  </td>
                  <td className="py-2 text-right font-mono text-slate-700">{r.conf.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </aside>
    </div>
  );
}

window.GraphEngine = GraphEngine;
