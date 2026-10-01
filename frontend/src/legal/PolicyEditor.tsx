import { useState } from 'react';
import type { Policy, ScenarioCatalog } from './types';
import { ScenarioOptions } from './ScenarioPicker';
import { currentScenario, usableCatalog } from './scenarioInput';
import { BookOpen } from 'lucide-react';
import { useI18n } from '../i18n/core';

type Draft = { title: string; text: string; contract_type: string; our_roles: string[] };
const EMPTY: Draft = { title: '', text: '', contract_type: '全部', our_roles: [] };

export function PolicyEditor({ catalog, policies, busy, onSave, onArchive }: {
  catalog?: ScenarioCatalog; policies: Policy[]; busy: boolean;
  onSave: (draft: Draft, existing: Policy | null) => void; onArchive: (policy: Policy) => void;
}) {
  const { tx, t } = useI18n();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<Policy | null>(null);
  const scene = currentScenario(catalog, draft.contract_type);
  const validScope = usableCatalog(catalog) && (draft.contract_type === '全部' || !!scene) && draft.our_roles.every(r => scene?.roles.some(x => x.value === r));
  return <main id="legal-main" tabIndex={-1} className="lv-policy-page">
    <div className="lv-policy-inner">
      <h1>{tx('公司规范', 'Company policies')}</h1>
      <p className="lv-page-meta">{tx('审查时逐条对照', 'Checked one by one in every review')}<span className="lv-sep" aria-hidden="true">·</span><span className="lv-mono">{policies.length}</span>{tx(' 条启用', ' active')}<span className="lv-sep" aria-hidden="true">·</span>{tx('仅组织管理员可编辑', 'Only organisation admins can edit')}</p>
      <div className="lv-policy-layout">
        <section className="lv-policy-list" aria-label={tx('已启用规范', 'Active policies')}>
          {!policies.length && <div className="lv-policy-empty"><span className="lv-tile is-gray" aria-hidden="true"><BookOpen size={28} strokeWidth={1.5} /></span><p>{tx('暂无公司规范', 'No company policies yet')}</p></div>}
          {policies.map(p => <article key={p.id}>
            <span className="lv-mono lv-policy-version">v{p.version}</span>
            <div className="lv-policy-main">
              <h3>{p.title}</h3>
              <p className="lv-policy-text">{p.text}</p>
              <span className="lv-policy-type">{p.contract_type === '全部' ? tx('全部合同', 'All contracts') : t(p.contract_type)} · {p.our_roles?.length ? p.our_roles.map(t).join(' / ') : tx('全部身份', 'All roles')}</span>
            </div>
            <div className="lv-policy-actions">
              <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={() => { setEditing(p); setDraft({ title: p.title, text: p.text, contract_type: p.contract_type, our_roles: p.our_roles || [] }); }}>{tx('编辑', 'Edit')}</button>
              <button className="lv-quiet lv-btn-sm" disabled={busy} onClick={() => onArchive(p)}>{tx('归档', 'Archive')}</button>
            </div>
          </article>)}
        </section>
        <form className="lv-policy-form" onSubmit={e => { e.preventDefault(); if (validScope && !busy) onSave(draft, editing); }}>
          <h2>{editing ? tx('编辑规范', 'Edit policy') : tx('新增规范', 'New policy')}</h2>
          <label className="lv-field"><span className="lv-field-label">{tx('规范名称', 'Policy name')}</span>
            <input className="lv-input" required maxLength={150} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} placeholder={tx('如：预付款比例上限', 'e.g. Cap on advance payments')} /></label>
          <label className="lv-field"><span className="lv-field-label">{tx('适用合同', 'Applies to')}</span>
            <select className="lv-select" aria-label={tx('规范适用合同', 'Contract types the policy applies to')} value={draft.contract_type} disabled={busy || !usableCatalog(catalog)} onChange={e => setDraft({ ...draft, contract_type: e.target.value, our_roles: [] })}>
              <option value="全部">{tx('全部合同', 'All contracts')}</option><ScenarioOptions catalog={catalog} />
            </select></label>
          {scene && <fieldset className="lv-field lv-fieldset" disabled={busy}>
            <legend className="lv-field-label">{tx('适用身份', 'Applies to roles')}<span className="lv-optional">{tx('不选则全部适用', 'none selected means all')}</span></legend>
            <div className="lv-check-pills">{scene.roles.map(role => <label key={role.value} className={draft.our_roles.includes(role.value) ? 'selected' : ''}>
              <input type="checkbox" checked={draft.our_roles.includes(role.value)} onChange={e => setDraft({ ...draft, our_roles: e.target.checked ? [...draft.our_roles, role.value] : draft.our_roles.filter(r => r !== role.value) })} />
              {t(role.value)}</label>)}</div>
          </fieldset>}
          {!validScope && <p className="lv-note is-warn" role="alert">{tx('适用范围与合同类型目录不匹配，请重新选择。', 'This scope does not match the contract type catalogue. Choose again.')}</p>}
          <label className="lv-field"><span className="lv-field-label">{tx('规范内容', 'Policy text')}</span>
            <textarea className="lv-textarea" required minLength={5} maxLength={2500} rows={5} value={draft.text} onChange={e => setDraft({ ...draft, text: e.target.value })}
              placeholder={tx('如：预付款超过合同总价 30% 时，须经业务负责人审批。', 'e.g. Advance payments above 30% of the contract price need the business owner’s approval.')} /></label>
          <div className="lv-policy-submit">
            <span className="lv-hint">{tx('保存后用于新的审查', 'Applies to new reviews once saved')}</span>
            <span className="lv-inline-actions">
              {editing && <button type="button" className="lv-quiet lv-btn-sm" onClick={() => { setEditing(null); setDraft(EMPTY); }}>{tx('取消编辑', 'Cancel')}</button>}
              <button className="lv-primary lv-btn-sm" disabled={busy || !validScope}>{tx('保存规范', 'Save policy')}</button>
            </span>
          </div>
        </form>
      </div>
    </div>
  </main>;
}
