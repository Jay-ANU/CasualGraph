import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { FileDown, PenLine, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../api/client';
import '../legal/LegalDesk.css';
import { ContractSheet } from '../legal/art';

type Access = { allowed: boolean; plan: string; required_plan: string };

const BENEFITS = [
  { icon: ShieldCheck, text: '合同自动脱敏，模型只接收脱敏文本' },
  { icon: PenLine, text: '逐条风险批注、修改建议与法律依据' },
  { icon: FileDown, text: '导出审查报告与 Word 修订版' },
];

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
      if (!cancelled) { setAccess(null); setError('无法验证会员权限，请稍后重试。'); }
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
      <Link to="/" className="lv-gate-brand"><img src="/brand/logo-mark.svg" alt="" width={22} height={22} />CausalGraph<span className="lv-rule-v" aria-hidden="true" /><span className="lv-gate-product">合同审查</span></Link>
      <ContractSheet size={56} />
      <h1>{checking ? '正在验证会员权限' : error ? '服务暂不可用' : '合同审查为 Max 会员专享'}</h1>
      {access && !error && <ul>{BENEFITS.map(({ icon: Icon, text }) => <li key={text}><Icon size={16} strokeWidth={1.75} aria-hidden="true" />{text}</li>)}</ul>}
      <p role="status">{error || (checking ? '请稍候…' : '如需开通，请联系管理员。')}</p>
      {!checking && <div className="lv-gate-actions">
        <Link to="/agent" className="lv-primary">返回研究工作台</Link>
        <button className="lv-secondary" onClick={() => { setAccess(null); setError(''); setAttempt(x => x + 1); }}>重新验证</button>
      </div>}
    </main>
  </div>;
}
