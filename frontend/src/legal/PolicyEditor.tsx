import { useState } from 'react';
import type { Policy, ScenarioCatalog } from './types';
import { ScenarioOptions } from './ScenarioPicker';
import { currentScenario, usableCatalog } from './scenarioInput';
import { PolicySheet } from './art';

type Draft = { title: string; text: string; contract_type: string; our_roles: string[] };
const EMPTY: Draft = { title: '', text: '', contract_type: '全部', our_roles: [] };

export function PolicyEditor({ catalog, policies, busy, onSave, onArchive }: {
  catalog?: ScenarioCatalog; policies: Policy[]; busy: boolean;
  onSave: (draft: Draft, existing: Policy | null) => void; onArchive: (policy: Policy) => void;
}) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<Policy | null>(null);
  const scene = currentScenario(catalog, draft.contract_type);
  const validScope = usableCatalog(catalog) && (draft.contract_type === '全部' || !!scene) && draft.our_roles.every(r => scene?.roles.some(x => x.value === r));
  return <main id="legal-main" tabIndex={-1} className="lv-policy-page">
    <div className="lv-policy-inner">
      <h1>公司规范</h1>
      <p className="lv-lede">审查时将逐条对照公司内部要求。</p>
      <div className="lv-policy-layout">
        <section className="lv-policy-list" aria-labelledby="legal-policy-list-title">
          <div className="lv-section-head"><h2 id="legal-policy-list-title">已启用</h2><span>{policies.length}</span></div>
          {!policies.length && <div className="lv-policy-empty"><PolicySheet /><p>暂无公司规范</p></div>}
          {policies.map(p => <article key={p.id}>
            <div className="lv-policy-title"><h3>{p.title}</h3><small>v{p.version}</small></div>
            <span className="lv-policy-type">{p.contract_type === '全部' ? '全部合同' : p.contract_type} · {p.our_roles?.length ? p.our_roles.join(' / ') : '全部身份'}</span>
            <p>{p.text}</p>
            <div className="lv-inline-actions">
              <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={() => { setEditing(p); setDraft({ title: p.title, text: p.text, contract_type: p.contract_type, our_roles: p.our_roles || [] }); }}>编辑</button>
              <button className="lv-text-button" disabled={busy} onClick={() => onArchive(p)}>归档</button>
            </div>
          </article>)}
        </section>
        <form className="lv-policy-form" onSubmit={e => { e.preventDefault(); if (validScope && !busy) onSave(draft, editing); }}>
          <h2>{editing ? '编辑规范' : '新增规范'}</h2>
          <label className="lv-field"><span className="lv-field-label">规范名称</span>
            <input className="lv-input" required maxLength={150} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} placeholder="如：预付款比例上限" /></label>
          <label className="lv-field"><span className="lv-field-label">适用合同</span>
            <select className="lv-select" aria-label="规范适用合同" value={draft.contract_type} disabled={busy || !usableCatalog(catalog)} onChange={e => setDraft({ ...draft, contract_type: e.target.value, our_roles: [] })}>
              <option value="全部">全部合同</option><ScenarioOptions catalog={catalog} />
            </select></label>
          {scene && <fieldset className="lv-field lv-fieldset" disabled={busy}>
            <legend className="lv-field-label">适用身份<span className="lv-optional">不选则全部适用</span></legend>
            <div className="lv-check-row">{scene.roles.map(role => <label key={role.value} className="lv-check">
              <input type="checkbox" checked={draft.our_roles.includes(role.value)} onChange={e => setDraft({ ...draft, our_roles: e.target.checked ? [...draft.our_roles, role.value] : draft.our_roles.filter(r => r !== role.value) })} />
              <span>{role.value}</span></label>)}</div>
          </fieldset>}
          {!validScope && <p className="lv-note is-warn" role="alert">适用范围与合同类型目录不匹配，请重新选择。</p>}
          <label className="lv-field"><span className="lv-field-label">规范内容</span>
            <textarea className="lv-textarea" required minLength={5} maxLength={2500} rows={6} value={draft.text} onChange={e => setDraft({ ...draft, text: e.target.value })}
              placeholder="如：预付款超过合同总价 30% 时，须经业务负责人审批。" /></label>
          <p className="lv-hint">仅组织管理员可编辑。</p>
          <div className="lv-inline-actions">
            <button className="lv-primary" disabled={busy || !validScope}>保存规范</button>
            {editing && <button type="button" className="lv-secondary" onClick={() => { setEditing(null); setDraft(EMPTY); }}>取消编辑</button>}
          </div>
        </form>
      </div>
    </div>
  </main>;
}
