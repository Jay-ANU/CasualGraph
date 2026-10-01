import type { ScenarioCatalog } from './types';
import { currentScenario, usableCatalog } from './scenarioInput';
import { useI18n } from '../i18n/core';

/** Contract types grouped as the catalogue groups them. The Chinese label stays the value sent to the API. */
export function ScenarioOptions({ catalog }: { catalog?: ScenarioCatalog | null }) {
  const { t } = useI18n();
  if (!usableCatalog(catalog)) return null;
  return <>{[...new Set(catalog.scenarios.map(s => s.group))].map(group => <optgroup key={group} label={t(group)}>
    {catalog.scenarios.filter(s => s.group === group).map(s => <option key={s.id} value={s.label}>{t(s.label)}</option>)}
  </optgroup>)}</>;
}

export function ScenarioPicker({ catalog, type, role, disabled, onType, onRole }: {
  catalog?: ScenarioCatalog | null; type: string; role: string; disabled: boolean;
  onType: (type: string) => void; onRole: (role: string) => void;
}) {
  const { lang, tx, t } = useI18n();
  const scene = currentScenario(catalog, type);
  const roles = scene?.roles.length || 1;
  // English role names run long, so they wrap onto rows instead of sharing one row.
  const columns = lang === 'en' ? `repeat(${Math.min(roles, 2)}, minmax(0, 1fr))` : `repeat(${Math.max(1, roles)}, minmax(0, 1fr))`;
  return <>
    <label className="lv-field"><span className="lv-field-label">{tx('合同类型', 'Contract type')}</span>
      <select className="lv-select" aria-label={tx('合同类型', 'Contract type')} value={type} disabled={disabled || !usableCatalog(catalog)} onChange={e => onType(e.target.value)}>
        {!scene && <option value={type}>{type ? t(type) : tx('选择合同类型', 'Choose a contract type')}{tx('（目录未匹配）', ' (not in the catalogue)')}</option>}
        <ScenarioOptions catalog={catalog} />
      </select>
      {!usableCatalog(catalog) && <p role="alert" className="lv-note is-warn">{tx('合同类型目录暂不可用，请刷新页面。', 'The contract type catalogue is unavailable. Refresh the page.')}</p>}
    </label>
    <fieldset className="lv-field lv-fieldset" disabled={disabled || !scene}>
      <legend className="lv-field-label">{tx('我方身份', 'Our role')}</legend>
      <div className="lv-segmented" role="radiogroup" aria-label={tx('我方身份', 'Our role')} style={{ gridTemplateColumns: columns }}>
        {scene?.roles.map(r => <label key={r.value} className={role === r.value ? 'selected' : ''}>
          <input type="radio" name="legal-our-role" value={r.value} checked={role === r.value} onChange={() => onRole(r.value)} />{t(r.value)}
        </label>)}
      </div>
      {role && scene && !scene.roles.some(r => r.value === role) && <p className="lv-note is-warn" role="alert">{tx(`“${role}”不适用于当前合同类型，请重新选择。`, `“${t(role)}” does not apply to this contract type. Choose again.`)}</p>}
    </fieldset>
  </>;
}
