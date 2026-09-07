import React, { useState } from 'react';
import { BookOpen, Maximize2, Minimize2 } from 'lucide-react';

const preferenceKey = 'causalgraph:research-focus:v1';

export default function ResearchWorkspace({ children }: { children: React.ReactNode }) {
  const [focus, setFocus] = useState(() => {
    try { return window.localStorage.getItem(preferenceKey) === 'true'; } catch { return false; }
  });
  const [showHelp, setShowHelp] = useState(false);
  const toggleFocus = () => {
    setFocus((current) => {
      const next = !current;
      try { window.localStorage.setItem(preferenceKey, String(next)); } catch { /* Private browsing must remain usable. */ }
      return next;
    });
  };

  return (
    <section className={`research-workspace-shell${focus ? ' research-focus' : ''}`} aria-label="ESG research workspace">
      <div className="research-workspace-toolbar">
        <div className="research-workspace-title"><BookOpen size={17} aria-hidden="true" /><strong>Research desk</strong><span>Evidence, connected.</span></div>
        <div className="research-workspace-tools">
          <button type="button" onClick={() => setShowHelp(!showHelp)} aria-expanded={showHelp} aria-controls="research-mode-help">Research guide</button>
          <button className="research-focus-toggle" type="button" onClick={toggleFocus} aria-pressed={focus} title={focus ? 'Show the research sidebar' : 'Hide the sidebar for focused reading'}>{focus ? <Minimize2 size={15} aria-hidden="true" /> : <Maximize2 size={15} aria-hidden="true" />}<span>{focus ? 'Show sidebar' : 'Focus view'}</span></button>
        </div>
      </div>
      {showHelp && <div className="research-mode-help" id="research-mode-help"><p><strong>Flash:</strong> focused retrieval and a direct answer. <strong>Deep:</strong> layered retrieval and graph context. Both modes use the configured DeepSeek model after the backend migration.</p><p>Select reports before asking a company-specific question. Open source citations to verify important claims. Missing evidence should stay visible, not be filled with guesses.</p></div>}
      {children}
    </section>
  );
}
