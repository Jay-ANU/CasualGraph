import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, apiFetch } from '../api/client';
import Agent from './Agent';
import ContractReview from './ContractReview';

/** A frontend release cannot replace the working app before its backend is ready. */
export default function AgentEntry() {
  const [state, setState] = useState<'loading' | 'legal' | 'legacy' | 'error'>('loading');
  useEffect(() => {
    let cancelled = false;
    apiFetch<{ product?: string }>('/legal/capabilities')
      .then(capability => { if (!cancelled) setState(capability.product === 'contract-review' ? 'legal' : 'legacy'); })
      .catch(error => { if (!cancelled) setState(error instanceof ApiError && error.status === 404 ? 'legacy' : 'error'); });
    return () => { cancelled = true; };
  }, []);
  if (state === 'loading') return <p role="status" className="p-8">正在连接工作台…</p>;
  if (state === 'legal') return <ContractReview />;
  if (state === 'legacy') return <><div role="status" className="bg-paper px-5 py-2 text-sm">法务后端尚未发布，当前保留资料问答。<Link to="/legal" className="ml-3 underline">查看法务工作台</Link></div><Agent /></>;
  return <div role="alert" className="p-8">暂时无法连接后端。请刷新重试；<Link to="/research" className="underline">进入原资料工作台</Link>。</div>;
}
