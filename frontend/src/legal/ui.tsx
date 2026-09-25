import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { RefreshCw, X } from 'lucide-react';
import type { Catalog } from './types';
import { splitRedactions } from './text';
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

/** A label/control row; controls carry their own accessible names. */
export function FormRow({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return <div className="lv-row">
    <div className="lv-row-label">{label}{note && <span className="lv-optional">{note}</span>}</div>
    <div className="lv-row-control">{children}</div>
  </div>;
}

/** Native modal supplies focus containment, Escape and return-focus behavior. */
export function ConfirmDialog({ title, children, confirmLabel, busy, onCancel, onConfirm }: {
  title: string; children: ReactNode; confirmLabel: string; busy: boolean;
  onCancel: () => void; onConfirm: () => void;
}) {
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
  return <dialog ref={ref} className="lv-dialog" aria-labelledby="lv-dialog-title"
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
      <button type="button" className="lv-icon" aria-label="关闭确认窗口" disabled={busy} onClick={onCancel}><X {...ic} size={18} /></button>
    </div>
    <div className="lv-dialog-body">{children}</div>
    <div className="lv-dialog-actions">
      <button ref={cancelRef} type="button" className="lv-secondary" disabled={busy} onClick={onCancel}>取消</button>
      <button type="button" className="lv-primary" disabled={busy} onClick={onConfirm}>{busy && <Spinner />}{busy ? '正在处理…' : confirmLabel}</button>
    </div>
  </dialog>;
}

export function ModelSelect({ catalog, value, loading, disabled, onChange, onRefresh }: {
  catalog: Catalog | null; value: string; loading: boolean; disabled: boolean;
  onChange: (id: string) => void; onRefresh: () => void;
}) {
  const families = catalog?.families.filter(family => catalog.models.some(m => m.family === family)) || [];
  return <div className="lv-model-control">
    <div className="lv-model">
      <select className="lv-select" aria-label="审查模型" value={value} disabled={disabled || loading || !catalog} onChange={e => onChange(e.target.value)}>
        <option value="" disabled>{loading ? '加载中…' : '选择模型'}</option>
        {families.map(family => <optgroup key={family} label={family}>
          {catalog?.models.filter(m => m.family === family).map(m => <option value={m.id} key={m.id}>{m.id}</option>)}
        </optgroup>)}
      </select>
      <button type="button" className="lv-icon" disabled={disabled || loading} title="刷新模型列表" aria-label="刷新模型列表" onClick={onRefresh}><RefreshCw {...ic} /></button>
    </div>
    {!!catalog?.unavailable_families?.length && <p className="lv-hint" role="status">{catalog.unavailable_families.join('、')} 暂不可用</p>}
  </div>;
}
