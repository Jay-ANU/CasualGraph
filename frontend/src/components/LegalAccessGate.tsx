import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import '../legal/LegalDesk.css';

type Access = { allowed: boolean; plan: string; required_plan: string };

const BENEFITS = ['上传合同，自动脱敏公司名称、联系人和账户', '按你的立场逐条找出风险，附依据和修改建议', '导出审查报告；Word 合同可导出带修订痕迹的版本'];

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
      if (!cancelled) { setAccess(null); setError('暂时无法确认会员状态，请稍后重试。'); }
    });
    void check();
    const timer = window.setInterval(() => void check(), 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [attempt]);
  // Never use localStorage's plan/role as authorization, even for the initial mount.
  if (access?.allowed === true && access.required_plan === 'max') return <>{children}</>;
  const checking = !access && !error;
  return <div className="lv-gate">
    <main className="lv-gate-card">
      <Link to="/" className="lv-gate-brand"><img src="/brand/logo-mark.svg" alt="" width={24} height={24} />CausalGraph</Link>
      <h1>{checking ? '正在确认会员状态' : error ? '合同审查暂时不可用' : '合同审查是 Max 会员功能'}</h1>
      <p role="status">{error || (checking ? '正在向服务器核验你的会员状态…' : 'Free 和 Pro 会员可以继续使用研究工作台。如需开通 Max，请联系管理员。')}</p>
      {access && !error && <ul>{BENEFITS.map(item => <li key={item}>{item}</li>)}</ul>}
      {!checking && <div className="lv-gate-actions">
        <Link to="/agent" className="lv-primary">返回研究工作台</Link>
        <button className="lv-secondary" onClick={() => { setAccess(null); setError(''); setAttempt(x => x + 1); }}>重新检查</button>
        <Link to="/" className="lv-text-button">网站首页</Link>
      </div>}
    </main>
  </div>;
}
