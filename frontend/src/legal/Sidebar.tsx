import type React from 'react';
import { ArrowLeft, BookOpen, FileText, LogOut, Plus, Search, X } from 'lucide-react';
import type { ContractSummary, Matter, User, Workspace } from './types';
import { CONTRACT_STATUS, fileTitle, formatDate } from './labels';
import { ic } from './icon';

type Props = {
  open: boolean; busy: boolean; loading: boolean; tab: 'review' | 'policies';
  user: User | null; matters: Matter[]; workspace: Workspace | null;
  contracts: ContractSummary[]; currentId?: string; policyCount: number;
  query: string; onQuery: (value: string) => void;
  onNew: () => void; onTab: (tab: 'review' | 'policies') => void; onOpen: (id: string) => void;
  onMatter: (id: string) => void; onClose: () => void; onLogout: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void;
};

export function Sidebar(p: Props) {
  const matches = p.contracts.filter(item => item.name.toLowerCase().includes(p.query.toLowerCase()));
  return <aside className="lv-sidebar" aria-label="合同审查导航" role={p.open ? 'dialog' : undefined} aria-modal={p.open || undefined}
    onKeyDown={p.onKeyDown} onTransitionEnd={event => {
      if (event.target === event.currentTarget && p.open && !event.currentTarget.contains(document.activeElement)) document.getElementById('legal-close-menu')?.focus();
    }}>
    <div className="lv-brand-row">
      <a href="/" className="lv-brand"><img src="/brand/logo-mark.svg" alt="" width={22} height={22} /><span>CausalGraph</span></a>
      <span className="lv-brand-product">合同审查</span>
      <button id="legal-close-menu" className="lv-icon lv-mobile-only" onClick={p.onClose} aria-label="关闭导航"><X {...ic} size={18} /></button>
    </div>
    <button className="lv-new" disabled={p.busy} onClick={p.onNew}><Plus {...ic} />新建审查</button>
    <nav className="lv-navigation" aria-label="法务工作台">
      <button className={p.tab === 'review' ? 'selected' : ''} aria-current={p.tab === 'review' ? 'page' : undefined} onClick={() => p.onTab('review')}><FileText {...ic} />合同审查</button>
      <button className={p.tab === 'policies' ? 'selected' : ''} aria-current={p.tab === 'policies' ? 'page' : undefined} onClick={() => p.onTab('policies')}><BookOpen {...ic} />公司规范<span className="lv-count">{p.policyCount}</span></button>
    </nav>
    {p.matters.length > 1 && <label className="lv-workspace"><span>工作空间</span>
      <select className="lv-select" aria-label="事项工作区" value={p.workspace?.matter_id || ''} disabled={p.busy} onChange={e => p.onMatter(e.target.value)}>
        {p.matters.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select></label>}
    <div className="lv-history-head">审查记录</div>
    <label className="lv-search"><Search {...ic} size={15} /><input aria-label="查找历史合同" placeholder="搜索合同" value={p.query} onChange={e => p.onQuery(e.target.value)} /></label>
    <div className="lv-history">
      {matches.map(item => <button key={item.id} disabled={p.busy} className={p.currentId === item.id ? 'selected' : ''} aria-current={p.currentId === item.id ? 'true' : undefined} onClick={() => p.onOpen(item.id)}>
        <span className="lv-history-name">{fileTitle(item.name)}</span>
        <span className="lv-history-meta"><i className={`lv-dot is-${item.status}`} aria-hidden="true" />{CONTRACT_STATUS[item.status] || item.status}{formatDate(item.created_at) && ` · ${formatDate(item.created_at)}`}</span>
      </button>)}
      {!p.loading && !p.contracts.length && <p>暂无记录</p>}
      {p.contracts.length > 0 && !matches.length && <p role="status">无匹配结果</p>}
    </div>
    <div className="lv-sidebar-bottom">
      <a href="/agent"><ArrowLeft {...ic} size={15} />返回研究工作台</a>
      <div className="lv-account">
        <span className="lv-avatar" aria-hidden="true">{(p.user?.username || p.user?.email || 'U').slice(0, 1).toUpperCase()}</span>
        <span className="lv-account-name">{p.user?.username || '我的账户'}<small>Max 会员</small></span>
        <button className="lv-icon" onClick={p.onLogout} aria-label="退出登录"><LogOut {...ic} /></button>
      </div>
    </div>
  </aside>;
}
