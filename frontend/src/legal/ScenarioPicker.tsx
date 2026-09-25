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
  const focus = scene?.roles.find(r => r.value === role)?.focus;
  return <div className="lv-scenario" aria-label="合同场景设置" role="group">
    {!usableCatalog(catalog) && <p role="alert" className="lv-note is-warn">合同类型目录暂时不可用，请刷新页面后再试。</p>}
    <label className="lv-field"><span className="lv-field-label">合同类型</span>
      <select className="lv-select" aria-label="合同类型" value={type} disabled={disabled || !usableCatalog(catalog)} onChange={e => onType(e.target.value)}>
        {!scene && <option value={type}>{type || '选择合同类型'}（目录未匹配）</option>}
        <ScenarioOptions catalog={catalog} />
      </select></label>
    <fieldset className="lv-field lv-fieldset" disabled={disabled || !scene}>
      <legend className="lv-field-label">你在这份合同中是</legend>
      <div className="lv-pills" role="radiogroup" aria-label="我方角色">
        {scene?.roles.map(r => <label key={r.value} className={`lv-pill ${role === r.value ? 'selected' : ''}`}>
          <input type="radio" name="legal-our-role" value={r.value} checked={role === r.value} onChange={() => onRole(r.value)} />{r.value}
        </label>)}
      </div>
      {role && scene && !scene.roles.some(r => r.value === role) && <p className="lv-note is-warn" role="alert">之前选择的“{role}”不适用于当前合同类型，请重新选择。</p>}
      <p className="lv-hint">{focus ? `从你的立场出发：${focus}` : '审查会站在你这一方的角度。合同标题不能决定你是谁，请按实际身份选择。'}</p>
    </fieldset>
    {scene && <details className="lv-disclosure lv-scenario-guide">
      <summary>这类合同会重点检查：{scene.checks.map(c => c.title).join('、')}</summary>
      <div className="lv-disclosure-body">
        <p>建议一并准备：{scene.materials.join('；')}。</p>
        <p className="lv-hint">{scene.limits} 更改类型或角色只影响新一轮审查，历史报告保留原设置。</p>
      </div>
    </details>}
  </div>;
}
