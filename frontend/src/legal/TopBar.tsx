import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, BookOpen, LogOut } from 'lucide-react';
import type { Matter, User, Workspace } from './types';
import { DrawnCheck } from './ui';
import { ic } from './icon';

export type Step = { label: string; state: 'done' | 'current' | 'todo'; onClick?: () => void };

function AccountMenu({ user, matters, workspace, busy, onMatter, onLogout }: {
  user: User | null; matters: Matter[]; workspace: Workspace | null; busy: boolean;
  onMatter: (id: string) => void; onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false); ref.current?.querySelector<HTMLButtonElement>('.lv-avatar')?.focus();
    };
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);
  const name = user?.username || user?.email || '我的账户';
  return <div className="lv-account" ref={ref}>
    <button className="lv-avatar" aria-expanded={open} aria-controls="legal-account-menu" aria-label={`账户：${name}`} onClick={() => setOpen(!open)}>
      {name.slice(0, 1).toUpperCase()}
    </button>
    {open && <div id="legal-account-menu" className="lv-account-menu" role="group" aria-label="账户">
      <p className="lv-account-name">{name}<small>Max 会员</small></p>
      {matters.length > 1 && <label className="lv-field"><span className="lv-field-label">工作空间</span>
        <select className="lv-select" aria-label="事项工作区" value={workspace?.matter_id || ''} disabled={busy}
          onChange={e => { setOpen(false); onMatter(e.target.value); }}>
          {matters.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select></label>}
      <a href="/agent" className="lv-menu-item"><ArrowLeft {...ic} size={15} />返回研究工作台</a>
      <button className="lv-menu-item" onClick={onLogout}><LogOut {...ic} size={15} />退出登录</button>
    </div>}
  </div>;
}

/** Brand and location on the left, the review's steps in the middle, the policy library and account on the right. */
export function TopBar({ section, steps, policyCount, onPolicies, policiesOpen, onHome, ...account }: {
  section?: string; steps?: Step[]; policyCount: number; policiesOpen: boolean;
  onHome: () => void; onPolicies: () => void;
  user: User | null; matters: Matter[]; workspace: Workspace | null; busy: boolean;
  onMatter: (id: string) => void; onLogout: () => void;
}) {
  return <header className="lv-topbar">
    <div className="lv-topbar-start">
      <a href="/" className="lv-brand"><img src="/brand/logo-mark.svg" alt="" width={22} height={22} /><span>CausalGraph</span></a>
      <span className="lv-rule-v" aria-hidden="true" />
      <nav className="lv-crumbs" aria-label="当前位置">
        <button onClick={onHome} disabled={account.busy} aria-current={section ? undefined : 'page'}>合同库</button>
        {section && <><span className="lv-crumb-sep" aria-hidden="true">/</span><span className="lv-crumb-current" aria-current="page" title={section}>{section}</span></>}
      </nav>
    </div>
    <div className="lv-topbar-mid">
      {steps && <ol className="lv-stepper" aria-label="合同审查步骤">{steps.map((step, i) => {
        const inner = <><span className="lv-step-dot" aria-hidden="true">{step.state === 'done' ? <DrawnCheck size={10} /> : i + 1}</span>{step.label}</>;
        return <li key={step.label} className={`is-${step.state}`} aria-current={step.state === 'current' ? 'step' : undefined}>
          {step.onClick ? <button onClick={step.onClick}>{inner}</button> : <span>{inner}</span>}
        </li>;
      })}</ol>}
    </div>
    <div className="lv-topbar-end">
      <button className={`lv-quiet lv-policy-link ${policiesOpen ? 'is-on' : ''}`} aria-pressed={policiesOpen} aria-label={`公司规范（${policyCount} 条）`} onClick={onPolicies}>
        <BookOpen {...ic} size={15} /><span className="lv-policy-label">公司规范</span><span className="lv-mono lv-muted">{policyCount}</span>
      </button>
      <AccountMenu {...account} />
    </div>
  </header>;
}
