import type { ScenarioCatalog } from './types';

export function usableCatalog(catalog?: ScenarioCatalog | null): catalog is ScenarioCatalog {
  return catalog?.version === 1 && /^[a-f0-9]{64}$/.test(catalog.revision)
    && Array.isArray(catalog.scenarios) && catalog.scenarios.length > 0;
}

export function currentScenario(catalog: ScenarioCatalog | null | undefined, type: string) {
  return usableCatalog(catalog) ? catalog.scenarios.find(s => s.label === type) : undefined;
}

export function scenarioRoleValid(catalog: ScenarioCatalog | null | undefined, type: string, role: string): boolean {
  return !!currentScenario(catalog, type)?.roles.some(item => item.value === role);
}

export function changeScenario(catalog: ScenarioCatalog | null | undefined, type: string) {
  if (!currentScenario(catalog, type)) throw new Error('场景目录不可用或类型已更新，请刷新后再试。');
  return { contractType: type, ourRole: '', consent: false };
}
