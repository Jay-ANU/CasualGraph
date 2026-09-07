import React, { createContext, useContext } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components, ExtraProps } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { RagSource } from '../../types/api';
import { normalizeStreamingMarkdown, formatSourceDocumentTitle } from '../../pages/agent/ragUi';
import { remarkSourceLinks } from './citations';

interface Props { content: string; sources: RagSource[]; onCitation: (source: RagSource) => void }
const CitationContext = createContext<Pick<Props, 'sources' | 'onCitation'> | null>(null);

// Stable component identity keeps citation buttons mounted when a drawer opens
// or closes. Defining this renderer inside ResearchAnswer would discard focus.
function SourceLink({ href, children, node, ...props }: React.ComponentProps<'a'> & ExtraProps) {
  const context = useContext(CitationContext);
  const match = /^#cg-source-(\d+)$/.exec(href || '');
  const source = match ? context?.sources[Number(match[1])] : undefined;
  return source && context ? <button type="button" className="research-citation" onClick={() => context.onCitation(source)}
    aria-label={`View source ${Number(match![1]) + 1}: ${formatSourceDocumentTitle(source)}`} title={formatSourceDocumentTitle(source)}>{children}</button>
    : <a {...props} href={href} rel="noreferrer">{children}</a>;
}
const markdownComponents: Components = { a: SourceLink };

/** Shared by the real conversation and the explicitly labeled product example. */
export default function ResearchAnswer({ content, sources, onCitation }: Props) {
  return <CitationContext.Provider value={{ sources, onCitation }}>
    <div className="cg-message-assistant research-answer prose max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkMath, [remarkSourceLinks, { sources }]]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]}
        components={markdownComponents}
      >{normalizeStreamingMarkdown(content)}</ReactMarkdown>
    </div>
  </CitationContext.Provider>;
}
