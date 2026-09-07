import React from 'react';
import { ArrowUpRight, FileText, FileUp, FolderOpen, GitBranch, Search, ShieldCheck } from 'lucide-react';

type Starter = { title: string; prompt: string; tier: 'flash' | 'deep' };
interface Props { reportCount: number; starters: Starter[]; onUpload: () => void; onLibrary: () => void; onPrompt: (starter: Starter) => void }
export default function WorkbenchWelcome({ reportCount, starters, onUpload, onLibrary, onPrompt }: Props) {
  const icons = [Search, GitBranch, ShieldCheck];
  return (
    <div className="research-welcome">
      <div className="research-welcome-mark" aria-hidden="true"><img src="/brand/logo-mark.svg" alt="" /></div>
      <div className="research-eyebrow"><span /> YOUR RESEARCH WORKSPACE</div>
      <h2>Better questions.<br /><em>Traceable answers.</em></h2>
      <p className="research-welcome-lead">Explore sustainability reports, connect the evidence, and see what supports every conclusion.</p>
      <div className="research-context-bar">
        <FileText size={17} /><span>{reportCount > 0 ? `${reportCount} report${reportCount === 1 ? '' : 's'} in your library` : 'Start with a report, or ask a general question'}</span>
        <button type="button" onClick={onLibrary}>View library <ArrowUpRight size={14} /></button>
      </div>
      <div className="research-starters">
        {starters.slice(0, 3).map((starter, index) => {
          const Icon = icons[index];
          return <button key={starter.title} type="button" onClick={() => onPrompt(starter)}>
            <span className="research-starter-top"><Icon size={18} /><span>{starter.tier === 'deep' ? 'DEEP RESEARCH' : 'QUICK QUESTION'}</span><ArrowUpRight size={15} /></span>
            <strong>{starter.title}</strong><span className="research-starter-prompt">{starter.prompt}</span>
          </button>;
        })}
      </div>
      <button type="button" className="research-upload-entry" onClick={onUpload}>
        <span className="research-upload-icon"><FileUp size={21} /></span>
        <span><strong>Bring your own evidence</strong><span>Upload a report to start a source-grounded conversation.</span></span>
        <FolderOpen size={19} />
      </button>
      <p className="research-evidence-note"><ShieldCheck size={14} /> Report-backed findings and general analysis stay clearly separated.</p>
    </div>
  );
}
