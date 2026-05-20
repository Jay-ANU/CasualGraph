/* global React, Panel, Button, EyebrowChip */

function Home({ onNavigate }) {
  const capabilities = [
    { icon: 'file-search', title: 'Report-grounded answers', description: 'Locate relevant passages first, then produce concise answers with evidence retained in context.' },
    { icon: 'network',     title: 'Causal knowledge graphs', description: 'Convert disclosures, commitments, risks, and metrics into connected entities and relationship paths.' },
    { icon: 'bar-chart-3', title: 'Research-grade summaries', description: 'Surface targets, emissions movements, governance controls, and risk signals in a reviewable format.' },
  ];

  const workflows = [
    'Upload sustainability reports, policies, or disclosures',
    'Query the indexed corpus across reports and entities',
    'Review the passages behind each answer',
    'Explore extracted entities, relationships, and graph structure',
  ];

  return (
    <div className="min-h-screen text-slate-950">
      <section className="tech-hero app-grid">
        <div className="mx-auto grid max-w-[1600px] gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8 lg:py-24">
          <div>
            <EyebrowChip icon={(p) => <i data-lucide="shield-check" {...p}></i>}>Evidence infrastructure for ESG research</EyebrowChip>
            <h1 className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight text-slate-950 sm:text-6xl">
              Read disclosures as connected evidence, not isolated PDFs.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
              CausalGraph gives analysts a controlled workspace for report search, scenario reasoning, and graph-based review of climate, governance, and operating-risk disclosures.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button onClick={() => onNavigate('desk')} iconRight={(p)=><i data-lucide="arrow-right" {...p}></i>}>Open research desk</Button>
              <Button variant="secondary" onClick={() => onNavigate('graph')}>View graph engine</Button>
            </div>
          </div>

          <Panel className="p-4">
            <div className="rounded-2xl border border-slate-200 bg-white/86 p-5 shadow-sm">
              <div className="flex items-center gap-3 border-b border-slate-200 pb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-950 text-white"><i data-lucide="database" className="h-5 w-5"></i></div>
                <div>
                  <div className="text-sm font-semibold text-slate-950">Active evidence set</div>
                  <div className="text-xs text-slate-500">Documents, chunks, entities, and graph links</div>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {workflows.map((item, index) => (
                  <div key={item} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white text-xs font-semibold text-slate-700">{index + 1}</div>
                    <p className="text-sm leading-6 text-slate-700">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      </section>

      <section className="mx-auto max-w-[1600px] px-4 py-16 sm:px-6 lg:px-8">
        <div className="mb-8 max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight text-slate-950">Built for disclosure review</h2>
          <p className="mt-3 text-base leading-7 text-slate-600">The platform keeps each answer close to the passages, entities, and graph links that shaped it, so review stays auditable.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {capabilities.map(cap => (
            <Panel key={cap.title} className="p-6">
              <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-700"><i data-lucide={cap.icon} className="h-5 w-5"></i></div>
              <h3 className="text-lg font-semibold text-slate-950">{cap.title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{cap.description}</p>
            </Panel>
          ))}
        </div>
      </section>
    </div>
  );
}

window.Home = Home;
