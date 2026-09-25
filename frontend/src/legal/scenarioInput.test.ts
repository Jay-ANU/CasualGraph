import { describe, expect, it } from 'vitest';
import { changeScenario, currentScenario, scenarioRoleValid, usableCatalog } from './scenarioInput';
import type { ScenarioCatalog, ContractScenario } from './types';

const make = (id: string, label: string, roles: string[]): ContractScenario => ({ id, label, group: 'test',
  roles: roles.map(value => ({ value, focus: '合成测试' })), materials: [], checks: [], limits: '测试', catalog_version: 1, catalog_revision: 'a'.repeat(64) });
const catalog: ScenarioCatalog = { version: 1, revision: 'a'.repeat(64), notice: 'test', scenarios: [
  make('sales', '销售合同', ['销售方', '购买方']), make('nda', '保密协议', ['披露方', '接收方', '双向保密方']),
] };
describe('scenario input', () => {
  it('never invents a fallback when the catalogue is unavailable', () => {
    expect(usableCatalog(null)).toBe(false);
    expect(usableCatalog({ ...catalog, version: 9 })).toBe(false);
    expect(currentScenario(null, '销售合同')).toBeUndefined();
    expect(scenarioRoleValid(null, '销售合同', '销售方')).toBe(false);
  });
  it('validates role against selected type rather than a union of all roles', () => {
    expect(scenarioRoleValid(catalog, '销售合同', '销售方')).toBe(true);
    expect(scenarioRoleValid(catalog, '销售合同', '披露方')).toBe(false);
    expect(scenarioRoleValid(catalog, '保密协议', '双向保密方')).toBe(true);
  });
  it('resets role and external consent on scenario change', () => {
    expect(changeScenario(catalog, '保密协议')).toEqual({ contractType: '保密协议', ourRole: '', consent: false });
    expect(() => changeScenario(catalog, '未知类型')).toThrow();
  });
  it('requires a catalogue revision and keeps source data unchanged', () => {
    const before = structuredClone(catalog);
    changeScenario(catalog, '销售合同');
    expect(catalog).toEqual(before);
    expect(usableCatalog({ ...catalog, revision: '' })).toBe(false);
  });
});
