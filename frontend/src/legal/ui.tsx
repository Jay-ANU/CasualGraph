import { useI18n } from '../i18n/useI18n';
import { useEffect, useRef } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { Check, RefreshCw, X } from 'lucide-react';
import type { Catalog } from './types';
import { splitRedactions } from './text';
import { phraseDiff } from './diff';
import { ic } from './icon';

export function Spinner() {
  return <span className="lv-spinner" aria-hidden="true" />;
}

/**
 * Contract text with redaction placeholders drawn as redaction marks. The
 * brackets stay in the DOM (visually hidden) so copied text and accessible
 * names still match the original placeholder.
 */
export function RichText({ text }: { text: string }) {
  return <>{splitRedactions(text).map((part, i) => part.kind === 'text' ? part.text
    : <span className="lv-redacted" key={i}><span className="lv-sr">【</span>{part.text.slice(1, -1)}<span className="lv-sr">】</span></span>)}</>;
}

/** A paragraph's revision as tracked changes: struck deletions, underlined insertions. */
export function Redline({ before, after }: { before: string; after: string }) {
  const { t } = useI18n();
  return <>{phraseDiff(before, after).map((part, i) => part.kind === 'del'
    ? <del key={i} className="lv-del"><span className="lv-sr">{t("删除：")}</span><RichText text={part.text} /></del>
    : part.kind === 'ins' ? <ins key={i} className="lv-ins"><span className="lv-sr">{t("新增：")}</span><RichText text={part.text} /></ins>
    : <RichText key={i} text={part.text} />)}</>;
}

/** A check mark that draws itself in when it first appears. */
export function DrawnCheck({ size = 12 }: { size?: number }) {
  return <svg className="lv-drawn-check" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={2.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" pathLength={1} /></svg>;
}

/**
 * A count that runs up when it appears and eases between values. The digits
 * are drawn by a CSS counter; the real value stays in the text for assistive
 * technology, copy and tests.
 */
export function CountUp({ value }: { value: number }) {
  return <><span className="lv-countup" style={{ '--lv-n': value } as CSSProperties} aria-hidden="true" /><span className="lv-sr">{value}</span></>;
}

/** A short confirmation at the bottom of the screen that clears itself. */
export function Toast({ text, done, onDone }: { text: string; done?: boolean; onDone: () => void }) {
  const { t } = useI18n();
  const finish = useRef(onDone);
  useEffect(() => { finish.current = onDone; });
  useEffect(() => {
    const timer = setTimeout(() => finish.current(), 2600);
    return () => clearTimeout(timer);
  }, [text]);
  return <div className="lv-toast" role="status">{done && <Check {...ic} size={15} />}{t(text)}</div>;
}

/** Native modal supplies focus containment, Escape and return-focus behavior. */
export function ConfirmDialog({ title, children, confirmLabel, busyLabel = '正在处理…', busy, onCancel, onConfirm }: {
  title: string; children: ReactNode; confirmLabel: string; busyLabel?: string; busy: boolean;
  onCancel: () => void; onConfirm: () => void;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    // React autofocus runs while the native dialog is still closed. Focus after showModal.
    cancelRef.current?.focus();
    const frame = requestAnimationFrame(() => cancelRef.current?.focus());
    return () => { cancelAnimationFrame(frame); dialog?.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} className={`lv-dialog ${busy ? 'is-busy' : ''}`} aria-labelledby="lv-dialog-title" aria-busy={busy || undefined}
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'));
      if (!items.length) { event.preventDefault(); return; }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if ((event.shiftKey && index <= 0) || (!event.shiftKey && (index === items.length - 1 || index < 0))) {
        event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0].focus();
      }
    }}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <div className="lv-dialog-heading">
      <h2 id="lv-dialog-title">{title}</h2>
      <button type="button" className="lv-icon" aria-label={t("关闭确认窗口")} disabled={busy} onClick={onCancel}><X {...ic} size={18} /></button>
    </div>
    <div className="lv-dialog-body">{children}</div>
    <div className="lv-dialog-actions">
      <button ref={cancelRef} type="button" className="lv-secondary" disabled={busy} onClick={onCancel}>{t("取消")}</button>
      <button type="button" className="lv-primary" disabled={busy} onClick={onConfirm}>{busy && <Spinner />}{t(busy ? busyLabel : confirmLabel)}</button>
    </div>
  </dialog>;
}

export function ModelSelect({ catalog, value, loading, disabled, onChange, onRefresh }: {
  catalog: Catalog | null; value: string; loading: boolean; disabled: boolean;
  onChange: (id: string) => void; onRefresh: () => void;
}) {
  const { t } = useI18n();
  const families = catalog?.families.filter(family => catalog.models.some(m => m.family === family)) || [];
  return <div className="lv-model-control">
    <div className="lv-model">
      <select className="lv-select" aria-label={t("审查模型")} value={value} disabled={disabled || loading || !catalog} onChange={e => onChange(e.target.value)}>
        <option value="" disabled>{loading ? t("加载中…") : t("选择模型")}</option>
        {families.map(family => <optgroup key={family} label={family}>
          {catalog?.models.filter(m => m.family === family).map(m => <option value={m.id} key={m.id}>{m.id}</option>)}
        </optgroup>)}
      </select>
      <button type="button" className="lv-icon" disabled={disabled || loading} title={t("刷新模型列表")} aria-label={t("刷新模型列表")} onClick={onRefresh}><RefreshCw {...ic} /></button>
    </div>
    {!!catalog?.unavailable_families?.length && <p className="lv-hint" role="status">{catalog.unavailable_families.join('、')}{' '}{t("暂不可用")}</p>}
  </div>;
}
