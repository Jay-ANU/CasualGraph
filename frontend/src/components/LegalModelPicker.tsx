import { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';

type Model = { id: string; family: string };
type Catalog = { models: Model[]; families: string[]; default_model: string; catalog_source: string; notice: string };

export default function LegalModelPicker({ value, onChange, disabled }: {
  value: string; onChange: (id: string) => void; disabled: boolean;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    apiFetch<Catalog>('/legal/models').then(data => {
      if (cancelled) return;
      setCatalog(data); setError(''); setLoading(false); onChange(data.default_model);
    }).catch(e => {
      if (cancelled) return;
      setCatalog(null); setError(e instanceof Error ? e.message : '模型列表加载失败。'); setLoading(false); onChange('');
    });
    return () => { cancelled = true; };
  }, [attempt, onChange]);
  return <section className="mt-5 mb-5 space-y-2" aria-label="YData 模型选择">
    <label className="block text-sm">审查模型 · Max<select aria-label="审查模型" value={value} disabled={disabled || loading || !catalog}
      onChange={e => onChange(e.target.value)} className="mt-2 block w-full min-w-0 rounded-md border border-line bg-white p-2 text-sm">
      <option value="">{loading ? '正在读取模型列表…' : '请选择模型'}</option>
      {catalog?.families.map(family => <optgroup key={family} label={family}>{catalog.models.filter(m => m.family === family).map(m => <option key={m.id} value={m.id}>{m.id}</option>)}</optgroup>)}
    </select></label>
    <p className="text-xs leading-relaxed text-ink-4">通过 YData 网关调用。选择用于新一轮审查，进行中的任务不会换模型。</p>
    {catalog && <p className="text-xs text-ink-4">{catalog.models.length} 个型号 · {catalog.catalog_source === 'gateway' ? '网关实时目录（短时缓存）' : '管理员配置目录'}</p>}
    {error && <p className="text-xs text-red-700" role="alert">{error}</p>}
    <button type="button" disabled={disabled || loading} className="text-xs underline" onClick={() => {
      setLoading(true); setError(''); onChange(''); setAttempt(x => x + 1);
    }}>刷新模型列表</button>
  </section>;
}
