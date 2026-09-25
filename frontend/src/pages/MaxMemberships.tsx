import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch, jsonRequest } from '../api/client';

type Membership = { user_id: string; email: string; expires_at: string | null; note: string; version: number };

export default function MaxMemberships() {
  const [rows, setRows] = useState<Membership[]>([]);
  const [email, setEmail] = useState('');
  const [expiry, setExpiry] = useState('');
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState<Membership | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const data = await apiFetch<{ memberships: Membership[] }>('/admin/max-memberships');
    setRows(data.memberships);
  }, []);
  useEffect(() => { void load().catch(e => setError(e instanceof Error ? e.message : '读取失败。')); }, [load]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : '操作失败。'); } finally { setBusy(false); }
  };
  return <main className="mx-auto max-w-content px-5 py-12 sm:px-8">
    <Link to="/admin" className="text-sm underline">返回管理后台</Link>
    <h1 className="display mt-6 text-display-sm">Max 会员</h1>
    <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-3">为已注册客户开通法务 Agent，不改变管理员身份或合同访问权限。会员到期或撤销后，法务接口和后续模型调用将被拦截。管理员原有 Max 权益不变。此处不处理支付。</p>
    {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}{notice && <p role="status" className="mt-4">{notice}</p>}
    <form className="panel mt-8 grid max-w-2xl gap-4 p-5" onSubmit={e => { e.preventDefault(); void run(async () => {
      if (!window.confirm(`确认${editing ? '更新' : '开通'} ${email} 的 Max 权限？`)) return;
      await apiFetch('/admin/max-memberships', jsonRequest('PUT', { email, note,
        expires_at: expiry ? new Date(expiry).toISOString() : null, expected_version: editing?.version || 0 }));
      await load(); setEditing(null); setEmail(''); setExpiry(''); setNote(''); setNotice('Max 权限已保存，客户刷新页面后生效。');
    }); }}>
      <h2 className="text-lg font-medium">{editing ? '更新会员' : '开通 Max'}</h2>
      <label className="text-sm">注册邮箱<input className="input mt-1" type="email" required maxLength={254} value={email} disabled={Boolean(editing)} onChange={e => setEmail(e.target.value)} /></label>
      <label className="text-sm">到期时间（本地时间；留空为长期有效）<input className="input mt-1" type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} /></label>
      <label className="text-sm">备注<input className="input mt-1" maxLength={500} value={note} onChange={e => setNote(e.target.value)} /></label>
      <div className="flex gap-2"><button className="btn btn-primary" disabled={busy}>保存 Max 权限</button>{editing && <button type="button" className="btn btn-secondary" onClick={() => { setEditing(null); setEmail(''); setExpiry(''); setNote(''); }}>取消</button>}</div>
    </form>
    <div className="mt-8 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b border-line"><th className="p-3">客户邮箱</th><th className="p-3">到期时间</th><th className="p-3">备注</th><th className="p-3">操作</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.user_id} className="border-b border-line"><td className="p-3">{row.email}</td><td className="p-3">{row.expires_at ? new Date(row.expires_at).toLocaleString() : '长期有效'}</td><td className="p-3">{row.note}</td><td className="p-3"><button className="mr-4 underline" disabled={busy} onClick={() => {
        setEditing(row); setEmail(row.email); setNote(row.note);
        const d = row.expires_at ? new Date(row.expires_at) : null;
        setExpiry(d ? new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '');
      }}>编辑</button><button className="underline" disabled={busy} onClick={() => void run(async () => {
        if (!window.confirm(`撤销 ${row.email} 的 Max 权限？已有合同不会删除。`)) return;
        await apiFetch(`/admin/max-memberships/${encodeURIComponent(row.user_id)}?version=${row.version}`, { method: 'DELETE' });
        await load(); setNotice('已撤销 Max 权限。');
      })}>撤销</button></td></tr>)}
    </tbody></table>{rows.length === 0 && <p className="py-6 text-ink-4">尚未添加客户 Max 授权。</p>}</div>
  </main>;
}
