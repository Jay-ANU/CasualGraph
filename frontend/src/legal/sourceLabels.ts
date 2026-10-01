import type { Source } from './types';
import { currentLang, type Lang } from '../i18n/core';
import { labelOf, type Pair } from './i18n';

const SOURCE_KIND: Record<string, Pair> = {
  normative_candidate: ['条文页候选', 'Likely statute page'], draft: ['草案／征求意见', 'Draft or consultation'], commentary: ['解读／问答', 'Commentary or Q&A'],
  case_material: ['案例材料', 'Case material'], unknown: ['类型待核验', 'Type to verify'],
};

export function sourceKindLabel(source: Source, lang: Lang = currentLang()): string {
  return labelOf(SOURCE_KIND, source.source_kind || 'unknown', lang) ?? labelOf(SOURCE_KIND, 'unknown', lang)!;
}
