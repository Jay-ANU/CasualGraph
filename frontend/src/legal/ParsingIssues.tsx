import { useI18n } from '../i18n/core';
import { serverText } from './i18n';
import { sourceLabel } from './documentLayout';
import type { Contract, SourceLocation } from './types';

export function ParsingIssues({ contract, onLocate }: { contract: Contract; onLocate: (location: SourceLocation) => void }) {
  const { tx } = useI18n();
  const issues = contract.document?.issues || [];
  const warnings = contract.warnings.filter(warning => !issues.some(issue => issue.message === warning));
  const count = issues.length + warnings.length;
  if (!count) return null;
  return <details className="lv-disclosure lv-parsing-issues">
    <summary>{tx(`解析提示（${count}）`, `Parsing notes (${count})`)}</summary>
    <div className="lv-disclosure-body">
      {issues.map(issue => <div className="lv-parsing-issue" key={issue.id}>
        <p>{serverText(issue.message)}</p>
        {(issue.block_id || issue.node_id || issue.asset_id || issue.page != null) && <button className="lv-text-button" onClick={() => onLocate(issue)}>
          {tx('查看位置：', 'Show location: ')}{sourceLabel(issue, contract.blocks.find(block => block.id === issue.block_id))}</button>}
      </div>)}
      {warnings.map((warning, i) => <p key={i}>{serverText(warning)}</p>)}
    </div>
  </details>;
}
