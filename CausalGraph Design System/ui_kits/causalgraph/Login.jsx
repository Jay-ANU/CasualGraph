/* global React, Panel, Button, Field, Input, EyebrowChip */
const { useState } = React;

function Login({ onSignIn }) {
  const [email, setEmail] = useState('analyst@causalgraph.ai');
  const [password, setPassword] = useState('••••••••');

  const submit = (e) => { e.preventDefault(); onSignIn({ email }); };

  return (
    <div className="min-h-screen tech-hero app-grid">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8">
        <div className="hidden lg:block">
          <EyebrowChip icon={(p) => <i data-lucide="shield-check" {...p}></i>}>Analyst sign-in</EyebrowChip>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-slate-950">Welcome back to the research desk.</h1>
          <p className="mt-4 max-w-md text-base leading-7 text-slate-600">
            Resume report search, scenario reasoning, and graph review where you left off — your indexed evidence set persists across sessions.
          </p>
          <div className="mt-8 grid gap-3">
            {[
              'Upload sustainability reports, policies, or disclosures',
              'Query the indexed corpus across reports and entities',
              'Review the passages behind each answer',
              'Explore extracted entities, relationships, and graph structure',
            ].map((item, i) => (
              <div key={item} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white text-xs font-semibold text-slate-700">{i + 1}</div>
                <p className="text-sm leading-6 text-slate-700">{item}</p>
              </div>
            ))}
          </div>
        </div>

        <Panel className="self-center p-7">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white"><i data-lucide="orbit" className="h-5 w-5"></i></div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">ESG Intelligence</div>
              <div className="text-lg font-semibold text-slate-950">Sign in to CausalGraph</div>
            </div>
          </div>
          <form onSubmit={submit} className="grid gap-4">
            <Field label="Work email"><Input value={email} onChange={(e)=>setEmail(e.target.value)} type="email" placeholder="you@firm.com" /></Field>
            <Field label="Password" hint="Use any value — this is a UI-kit demo, no auth wired up."><Input value={password} onChange={(e)=>setPassword(e.target.value)} type="password" /></Field>
            <Button type="submit" iconRight={(p)=><i data-lucide="arrow-right" {...p}></i>}>Continue to research desk</Button>
            <div className="text-center text-[12px] text-slate-500">By continuing you accept the audit-log and review controls.</div>
          </form>
        </Panel>
      </div>
    </div>
  );
}

window.Login = Login;
