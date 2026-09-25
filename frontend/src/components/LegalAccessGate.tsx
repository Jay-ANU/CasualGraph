import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';

type Access = { allowed: boolean; plan: string; required_plan: string };

export default function LegalAccessGate({ children }: { children: ReactNode }) {
  const [access, setAccess] = useState<Access | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const check = () => apiFetch<Access>('/legal/access').then(result => {
      if (!cancelled) {
        setAccess(result); setError('');
      }
    }).catch(() => {
      if (!cancelled) { setAccess(null); setError('暂时无法确认法务权限，请稍后重试或联系管理员。'); }
    });
    void check();
    const timer = window.setInterval(() => void check(), 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [attempt]);
  // Never use localStorage's plan/role as authorization, even for the initial mount.
  if (access?.allowed === true && access.required_plan === 'max') return <>{children}</>;
  return <div className="mx-auto max-w-content px-5 py-24 sm:px-8">
    <Link to="/" className="text-sm text-ink-3">CausalGraph</Link>
    <p className="mt-12 font-mono text-xs text-ink-4">LEGAL / MAX</p>
    <h1 className="display mt-4 text-display-sm">{access ? '法务 Agent · Max 专属' : error ? '法务服务暂不可用' : '正在确认访问权限'}</h1>
    <p className="mt-5 max-w-xl leading-relaxed text-ink-3" role="status">{error || (access ? '合同上传、脱敏、审查、模型选择与修订稿导出仅向有效的 Max 用户开放。Free 和 Pro 用户仍可使用原有研究工作台。请联系管理员开通 Max。' : '正在向服务器核验会员状态。')}</p>
    <div className="mt-8 flex flex-wrap gap-3"><Link to="/agent" className="btn btn-primary">返回研究工作台</Link><Link to="/" className="btn btn-secondary">网站首页</Link>
      <button className="btn btn-secondary" onClick={() => { setAccess(null); setError(''); setAttempt(x => x + 1); }}>重新检查权限</button></div>
  </div>;
}
