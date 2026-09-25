import type { ScenarioCatalog } from './types';
import { currentScenario, usableCatalog } from './scenarioInput';

export function ScenarioOptions({ catalog }: { catalog?: ScenarioCatalog | null }) {
  if (!usableCatalog(catalog)) return null;
  return <>{[...new Set(catalog.scenarios.map(s => s.group))].map(group => <optgroup key={group} label={group}>
    {catalog.scenarios.filter(s => s.group === group).map(s => <option key={s.id} value={s.label}>{s.label}</option>)}
  </optgroup>)}</>;
}

export function ScenarioPicker({ catalog, type, role, disabled, onType, onRole }: {
  catalog?: ScenarioCatalog | null; type: string; role: string; disabled: boolean;
  onType: (type: string) => void; onRole: (role: string) => void;
}) {
  const scene = currentScenario(catalog, type);
  return <section className="lv-scenario-picker" aria-label="合同场景设置">
    {!usableCatalog(catalog) && <p role="alert" className="lv-inline-warning">合同场景目录未就绪，请先升级后端或刷新页面；不能用旧选项发起新版审查。</p>}
    <div className="lv-fields">
      <label>合同类型<select aria-label="合同类型" value={type} disabled={disabled || !usableCatalog(catalog)} onChange={e => onType(e.target.value)}>
        {!scene && <option value={type}>{type || '选择合同类型'}（目录未匹配）</option>}
        <ScenarioOptions catalog={catalog} />
      </select></label>
      <label>我方角色<select aria-label="我方角色" value={role} disabled={disabled || !scene} onChange={e => onRole(e.target.value)}>
        <option value="">选择我方在交易中的身份</option>
        {role && !scene?.roles.some(r => r.value === role) && <option value={role} disabled>{role}（请重新选择）</option>}
        {scene?.roles.map(r => <option key={r.value} value={r.value}>{r.value}</option>)}
      </select></label>
    </div>
    {scene && <details className="lv-scenario-guide">
      <summary>本场景专项检查 · {scene.checks.map(c => c.title).join(' / ')}</summary>
      <p>{scene.roles.find(r => r.value === role)?.focus || '先明确我方角色，再从我方立场审查；合同标题不决定我方是谁。'}</p>
      <p>建议核对材料：{scene.materials.join('；')}。</p>
      <small>{scene.limits} 更改类型或角色仅用于新一轮审查，历史报告保留原设置。</small>
    </details>}
  </section>;
}
