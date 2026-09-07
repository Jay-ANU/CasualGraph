import React from 'react';
import { ArrowRight, FileUp } from 'lucide-react';
type Starter = { title: string; prompt: string; tier: 'flash' | 'deep' };
interface Props { reportCount: number; starters: Starter[]; onUpload: () => void; onLibrary: () => void; onPrompt: (starter: Starter) => void }
export default function WorkbenchWelcome({ reportCount, starters, onUpload, onLibrary, onPrompt }: Props) {
  return <div className="research-welcome">
    <h2>What are you researching?</h2>
    <p>{reportCount ? `${reportCount} report${reportCount === 1 ? '' : 's'} in your library. Select your sources below, then ask a question.` : 'Start with a report, or ask a general question'}</p>
    <div className="research-welcome-actions"><button type="button" onClick={onUpload} aria-label="Bring your own evidence"><FileUp size={16} />Upload a report</button><button type="button" onClick={onLibrary}>View library <ArrowRight size={14} /></button></div>
    <div className="research-starters" aria-label="Suggested questions">{starters.slice(0, 3).map(starter => <button type="button" key={starter.title} onClick={() => onPrompt(starter)}><span>{starter.prompt}</span><ArrowRight size={14} /></button>)}</div>
  </div>;
}
