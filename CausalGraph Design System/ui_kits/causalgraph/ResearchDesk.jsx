/* global React, Panel, Button, Pill, IconButton, Tag, DomainTag */
const { useState, useRef, useEffect } = React;

const SAMPLE_DOCS = [
  { id: 'bhp-2024',  title: 'BHP Sustainability Report',     subtitle: 'FY2024 · 168 pages',  domain: 'Environmental', synced: true,  active: true,  ingested: '2 hours ago',  chunks: 412, entities: 184 },
  { id: 'rio-2024',  title: 'Rio Tinto Climate Report',      subtitle: 'FY2024 · 92 pages',   domain: 'Environmental', synced: true,  active: false, ingested: 'Yesterday',     chunks: 248, entities: 121 },
  { id: 'fmg-2024',  title: 'Fortescue Climate Action Plan', subtitle: 'CY2024 · 60 pages',   domain: 'Governance',    synced: false, active: false, ingested: '3 days ago',    chunks: 184, entities: 88  },
];

const SEED_THREAD = [
  {
    role: 'user',
    text: 'Compare BHP and Rio Tinto on scope 1 reduction targets — show me the source paragraphs.',
    mode: 'ask',
  },
  {
    role: 'agent',
    text: "Both miners commit to a 30% operational-emissions reduction by FY2030 (vs FY2020), but **BHP's wording is narrower** — \"majority-owned and operated assets\" — while Rio Tinto extends the same target to \"managed operations.\"  Neither has published a public scope 3 reduction commitment as of FY2024.",
    sources: [
      { doc: 'bhp-2024-sustainability.pdf', page: 42, section: '§3.1', quote: '…reduce operational greenhouse gas emissions by at least 30% from FY2020 levels by FY2030…' },
      { doc: 'bhp-ctap-2024.pdf',           page: 6,  section: 'Table 1', quote: 'Operational emissions cover scopes 1 and 2 from majority-owned and operated assets.' },
      { doc: 'rio-tinto-climate-report-2024.pdf', page: 11, section: '§2.4', quote: '…30% reduction target applies to all managed operations on a 2018 baseline.' },
    ],
    graph: {
      nodes: [
        { id: 'bhp',     label: 'BHP',           x: 60,  y: 50,  domain: 'Environmental' },
        { id: 'rio',     label: 'Rio Tinto',     x: 60,  y: 170, domain: 'Environmental' },
        { id: 'scope1',  label: 'scope_1',       x: 200, y: 110, domain: 'General' },
        { id: 't_bhp',   label: '-30% FY30',     x: 340, y: 50,  domain: 'Environmental' },
        { id: 't_rio',   label: '-30% FY30 (m)', x: 340, y: 170, domain: 'Environmental' },
      ],
      edges: [
        { from: 'bhp', to: 'scope1', label: 'DISCLOSES' },
        { from: 'rio', to: 'scope1', label: 'DISCLOSES' },
        { from: 'scope1', to: 't_bhp', label: 'HAS_TARGET (BHP)' },
        { from: 'scope1', to: 't_rio', label: 'HAS_TARGET (RIO)' },
      ],
    },
  },
];

function ResearchDesk() {
  const [docs] = useState(SAMPLE_DOCS);
  const [activeDoc, setActiveDoc] = useState(SAMPLE_DOCS[0]);
  const [thread, setThread] = useState(SEED_THREAD);
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState('ask');
  const [attached, setAttached] = useState(['bhp-2024-sustainability.pdf', 'rio-tinto-climate-report-2024.pdf']);
  const endRef = useRef(null);

  useEffect(() => { window.lucide && window.lucide.createIcons(); }, [thread, mode]);
  useEffect(() => { endRef.current && endRef.current.scrollIntoView ? null : null; }, [thread]);

  const send = () => {
    if (!draft.trim()) return;
    const userMsg = { role: 'user', text: draft, mode };
    const agentMsg = mode === 'predict'
      ? {
          role: 'agent',
          text: `**Prediction · ${draft.slice(0, 60)}…**\n\nIf BHP holds its FY2030 trajectory, FY2027 scope 1 should land near **17.4 MtCO₂e** (mid-band). Sensitivity is dominated by the iron-ore haul-fleet electrification schedule (±2.1 Mt) and divestment timing of metallurgical-coal assets (±0.8 Mt).`,
          sources: [{ doc: 'bhp-2024-sustainability.pdf', page: 51, section: 'Fig. 7', quote: 'Operational emissions trajectory chart, FY2020–FY2030.' }],
        }
      : {
          role: 'agent',
          text: `Working on **"${draft.slice(0, 80)}"** — pulled 4 passages and 6 graph paths. Below is the synthesis with citations.`,
          sources: [{ doc: 'bhp-2024-sustainability.pdf', page: 42, section: '§3.1', quote: '…reduce operational greenhouse gas emissions by at least 30% from FY2020 levels by FY2030…' }],
        };
    setThread([...thread, userMsg, agentMsg]);
    setDraft('');
  };

  return (
    <div className="grid h-[calc(100vh-72px)] grid-cols-[280px_1fr_360px] bg-slate-50">
      {/* LEFT — Report library */}
      <aside className="flex flex-col border-r border-slate-200 bg-white/72 backdrop-blur">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Reports · {docs.length}</div>
          <IconButton icon={(p)=><i data-lucide="upload" {...p}></i>} label="Upload report" />
        </div>
        <div className="border-b border-slate-200 px-4 py-3">
          <Button size="sm" className="w-full" icon={(p)=><i data-lucide="plus" {...p}></i>}>New chat</Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {docs.map(doc => (
            <div key={doc.id} onClick={()=>setActiveDoc(doc)}
                 className={`mb-1 cursor-pointer rounded-lg border px-3 py-3 transition ${activeDoc.id===doc.id ? 'border-slate-300 bg-white shadow-sm' : 'border-transparent hover:bg-white/72'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-slate-900">{doc.title}</div>
                  <div className="truncate text-[11.5px] text-slate-500 font-mono">{doc.subtitle}</div>
                </div>
                {doc.synced ? <i data-lucide="check-circle-2" className="h-3.5 w-3.5 text-emerald-600 mt-0.5"></i> : <i data-lucide="loader-2" className="h-3.5 w-3.5 text-amber-500 mt-0.5"></i>}
              </div>
              <div className="mt-2 flex items-center gap-1.5">
                <DomainTag domain={doc.domain} />
                <span className="text-[10.5px] font-mono text-slate-400">{doc.entities} entities</span>
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-slate-200 px-4 py-3 text-[10.5px] font-mono text-slate-500">
          <div className="flex items-center gap-1.5"><i data-lucide="git-branch" className="h-3 w-3"></i> Neo4j · synced · auto</div>
        </div>
      </aside>

      {/* MIDDLE — Chat */}
      <section className="flex flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white/86 backdrop-blur px-6 py-3">
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-slate-950">Compare BHP & Rio Tinto · scope 1 targets</div>
            <div className="text-[12px] text-slate-500 font-mono">Active · {activeDoc.title} · {activeDoc.entities} entities</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" icon={(p)=><i data-lucide="download" {...p}></i>}>Export JSON</Button>
            <IconButton icon={(p)=><i data-lucide="trash-2" {...p}></i>} label="Delete chat" />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {thread.map((m, i) => (
              <Message key={i} message={m} />
            ))}
            <div ref={endRef} />
          </div>
        </div>

        <div className="border-t border-slate-200 bg-white/86 backdrop-blur px-6 py-4">
          <div className="mx-auto max-w-3xl">
            <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.06)]">
              {attached.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {attached.map(f => (
                    <span key={f} className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-[12px] font-mono text-slate-700">
                      <i data-lucide="file-text" className="h-3 w-3"></i>{f}
                      <button onClick={()=>setAttached(attached.filter(x=>x!==f))}><i data-lucide="x" className="h-3 w-3"></i></button>
                    </span>
                  ))}
                </div>
              )}
              <textarea value={draft} onChange={(e)=>setDraft(e.target.value)} rows={2}
                placeholder="Ask about a metric, target, or governance control…"
                className="w-full resize-none border-0 bg-transparent text-[14px] leading-6 text-slate-900 placeholder:text-slate-400 outline-none" />
              <div className="mt-2 flex items-center gap-2">
                <Pill icon={(p)=><i data-lucide="paperclip" {...p}></i>}>Attach</Pill>
                <Pill icon={(p)=><i data-lucide="message-square" {...p}></i>} active={mode==='ask'} onClick={()=>setMode('ask')}>Ask</Pill>
                <Pill icon={(p)=><i data-lucide="zap" {...p}></i>} active={mode==='predict'} onClick={()=>setMode('predict')}>Predict</Pill>
                <Pill icon={(p)=><i data-lucide="git-branch" {...p}></i>} active={mode==='graph'} onClick={()=>setMode('graph')}>Reason on graph</Pill>
                <div className="ml-auto">
                  <Button size="sm" onClick={send} iconRight={(p)=><i data-lucide="arrow-up" {...p}></i>}>Send</Button>
                </div>
              </div>
            </div>
            <div className="mt-2 text-[11px] font-mono text-slate-400 text-center">Answers cite the passages they were grounded on.</div>
          </div>
        </div>
      </section>

      {/* RIGHT — Evidence */}
      <aside className="flex flex-col border-l border-slate-200 bg-white/72 backdrop-blur">
        <div className="border-b border-slate-200 px-5 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Evidence · last answer</div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {(thread[thread.length-1].sources || []).map((s, i) => (
            <div key={i}>
              <div className="mb-1 flex items-center gap-1.5 font-mono text-[10.5px] text-slate-500">
                <i data-lucide="file-text" className="h-3 w-3"></i> {s.doc} · p.{s.page} · {s.section}
              </div>
              <div className="rounded-md border-l-2 border-slate-400 bg-white px-3 py-2 text-[13px] leading-6 text-slate-800">
                "{s.quote}"
              </div>
            </div>
          ))}

          {thread[thread.length-1].graph && (
            <div className="mt-2">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Graph trace</div>
              <MiniGraph data={thread[thread.length-1].graph} />
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Message({ message: m }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-slate-950 px-4 py-3 text-[14px] leading-6 text-white">
          {m.text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white"><i data-lucide="orbit" className="h-4 w-4"></i></div>
      <div className="min-w-0 flex-1">
        <div className="prose prose-sm max-w-none text-[14px] leading-7 text-slate-800" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.text) }} />
        {m.sources && m.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10.5px] font-mono uppercase tracking-[0.14em] text-slate-500">Cites</span>
            {m.sources.map((s, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-600">
                <i data-lucide="file-text" className="h-3 w-3"></i> {s.doc.split('-')[0]} · p.{s.page}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function renderMarkdown(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^/, '<p>').replace(/$/, '</p>');
}

function MiniGraph({ data }) {
  const W = 320, H = 220;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg border border-slate-200 bg-white">
      {data.edges.map((e, i) => {
        const a = data.nodes.find(n=>n.id===e.from);
        const b = data.nodes.find(n=>n.id===e.to);
        return <g key={i}>
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#94a3b8" strokeWidth="1.4" />
          <text x={(a.x+b.x)/2} y={(a.y+b.y)/2 - 4} textAnchor="middle" fill="#475569" fontSize="9" fontFamily="IBM Plex Mono, monospace">{e.label}</text>
        </g>;
      })}
      {data.nodes.map(n => {
        const fills = { Environmental:'#ecfdf5', Social:'#eff6ff', Governance:'#fff7ed', General:'#ffffff', AI:'#f5f3ff' };
        const strokes = { Environmental:'#047857', Social:'#1d4ed8', Governance:'#b45309', General:'#0f172a', AI:'#6d28d9' };
        return <g key={n.id}>
          <circle cx={n.x} cy={n.y} r="22" fill={fills[n.domain]} stroke={strokes[n.domain]} strokeWidth="1.5" />
          <text x={n.x} y={n.y+3} textAnchor="middle" fontSize="9.5" fontFamily="IBM Plex Mono, monospace" fill="#0f172a">{n.label}</text>
        </g>;
      })}
    </svg>
  );
}

window.ResearchDesk = ResearchDesk;
