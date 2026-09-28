import { useI18n } from '../i18n/useI18n';
import type { ScenarioCatalog } from './types';
import { currentScenario, usableCatalog } from './scenarioInput';

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
  const { t } = useI18n();
  const scene = currentScenario(catalog, type);
  return <>
    <label className="lv-field"><span className="lv-field-label">{t("合同类型")}</span>
      <select className="lv-select" aria-label={t("合同类型")} value={type} disabled={disabled || !usableCatalog(catalog)} onChange={e => onType(e.target.value)}>
        {!scene && <option value={type}>{type || t("选择合同类型")}{t("（目录未匹配）")}</option>}
        <ScenarioOptions catalog={catalog} />
      </select>
      {!usableCatalog(catalog) && <p role="alert" className="lv-note is-warn">{t("合同类型目录暂不可用，请刷新页面。")}</p>}
    </label>
    <fieldset className="lv-field lv-fieldset" disabled={disabled || !scene}>
      <legend className="lv-field-label">{t("我方身份")}</legend>
      <div className="lv-segmented" role="radiogroup" aria-label={t("我方身份")} style={{ gridTemplateColumns: `repeat(${Math.max(1, scene?.roles.length || 1)}, minmax(0, 1fr))` }}>
        {scene?.roles.map(r => <label key={r.value} className={role === r.value ? 'selected' : ''}>
          <input type="radio" name="legal-our-role" value={r.value} checked={role === r.value} onChange={() => onRole(r.value)} />{t(r.value)}
        </label>)}
      </div>
      {role && scene && !scene.roles.some(r => r.value === role) && <p className="lv-note is-warn" role="alert">“{role}{t("”不适用于当前合同类型，请重新选择。")}</p>}
    </fieldset>
  </>;
}
