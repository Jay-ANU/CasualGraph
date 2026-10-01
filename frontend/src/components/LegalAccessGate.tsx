import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { FileDown, FileText, PenLine, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../api/client';
import '../legal/LegalDesk.css';
import { useI18n } from '../i18n/core';
import LanguageSwitch from './LanguageSwitch';

type Access = { allowed: boolean; plan: string; required_plan: string };

const BENEFITS = [
  { icon: ShieldCheck, zh: '合同自动脱敏，模型只接收脱敏文本', en: 'Contracts are redacted automatically; models only see redacted text' },
  { icon: PenLine, zh: '逐条风险批注、修改建议与法律依据', en: 'Risk notes, suggested edits and the legal basis, clause by clause' },
  { icon: FileDown, zh: '导出审查报告与 Word 修订版', en: 'Export the review report and a tracked-changes Word file' },
];
// Kept in Chinese in state, like the desk's own messages, and translated when shown.
const ACCESS_ERROR = '无法验证会员权限，请稍后重试。';

export default function LegalAccessGate({ children }: { children: ReactNode }) {
  const { lang, tx, t } = useI18n();
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
      if (!cancelled) { setAccess(null); setError(ACCESS_ERROR); }
    });
    void check();
    const timer = window.setInterval(() => void check(), 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [attempt]);
  // Never use localStorage's plan/role as authorization, even for the initial mount.
  if (access?.allowed === true && access.required_plan === 'max') return <>{children}</>;
  const checking = !access && !error;
  return <div className={`lv-gate${lang === 'en' ? ' lv-en' : ''}`}>
    <main className="lv-gate-card">
      <div className="lv-gate-top">
        <Link to="/" className="lv-gate-brand"><img src="/brand/logo-mark.svg" alt="" width={22} height={22} />CausalGraph<span className="lv-rule-v" aria-hidden="true" /><span className="lv-gate-product">{tx('合同审查', 'Contract review')}</span></Link>
        <LanguageSwitch className="lv-lang" />
      </div>
      <span className="lv-tile lv-tile-lg is-blue" aria-hidden="true"><FileText size={34} strokeWidth={1.5} /></span>
      <h1>{checking ? tx('正在验证会员权限', 'Checking your membership') : error ? tx('服务暂不可用', 'Service unavailable') : tx('合同审查为 Max 会员专享', 'Contract review is part of the Max plan')}</h1>
      {access && !error && <ul>{BENEFITS.map(({ icon: Icon, zh, en }) => <li key={zh}><Icon size={16} strokeWidth={1.75} aria-hidden="true" />{tx(zh, en)}</li>)}</ul>}
      <p role="status">{error ? t(error) : checking ? tx('请稍候…', 'One moment…') : tx('如需开通，请联系管理员。', 'To get access, contact your administrator.')}</p>
      {!checking && <div className="lv-gate-actions">
        <Link to="/agent" className="lv-primary">{tx('返回研究工作台', 'Back to research desk')}</Link>
        <button className="lv-secondary" onClick={() => { setAccess(null); setError(''); setAttempt(x => x + 1); }}>{tx('重新验证', 'Check again')}</button>
      </div>}
    </main>
  </div>;
}
