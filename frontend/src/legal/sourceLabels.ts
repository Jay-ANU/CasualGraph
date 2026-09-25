import type { Source } from './types';

export function sourceKindLabel(source: Source): string {
  return ({ normative_candidate: '条文页候选', draft: '草案／征求意见', commentary: '解读／问答', case_material: '案例材料', unknown: '类型待核验' } as Record<string, string>)[source.source_kind || 'unknown'] || '类型待核验';
}
