import { BookOpen, Calculator, CalendarDays, FileSearch, FileText, Scale, ShieldCheck, Wrench } from 'lucide-react';
import type { ToolCall } from './types';
import { toolAction, toolOutcome } from './toolCalls';
import { Spinner } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';

const ICON: Record<string, typeof Wrench> = {
  search_law: Scale, read_law_article: BookOpen, find_in_contract: FileSearch, read_paragraphs: FileText,
  calculate: Calculator, date_calc: CalendarDays, check_revision: ShieldCheck,
};

/** The tools the model called, one line each, the way a chat app lists its searches and steps. */
export function ToolList({ calls, label }: { calls: ToolCall[]; label: string }) {
  const { lang } = useI18n();
  return <ol className="lv-tools" aria-label={label}>{calls.map((call, index) => {
    const outcome = toolOutcome(call, lang);
    const Icon = ICON[call.name] ?? Wrench;
    return <li key={`${call.step}:${index}:${call.id}`} className={`lv-tool is-${outcome.tone}`}>
      <span className="lv-tool-icon">{outcome.tone === 'running' ? <Spinner /> : <Icon {...ic} size={13} />}</span>
      <span className="lv-tool-action">{toolAction(call, lang)}</span>
      {call.detail && <span className="lv-tool-detail" lang="zh-CN">{call.detail}</span>}
      <span className="lv-tool-outcome">{outcome.text}</span>
    </li>;
  })}</ol>;
}
