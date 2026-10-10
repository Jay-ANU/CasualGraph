import { createContext, useContext, useMemo } from 'react';
import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Block, Review } from './types';
import { linkParagraphs } from './text';
import { useI18n } from '../i18n/core';

// Paragraph clicks go through context so the markdown components stay the same between renders.
const LocateContext = createContext<(blockId: string) => void>(() => undefined);

type LinkProps = ComponentPropsWithoutRef<'a'> & { node?: unknown };

// eslint-disable-next-line @typescript-eslint/no-unused-vars -- `node` is react-markdown's AST node; it must not reach the <a>
const MemoLink = ({ href, children, node, ...rest }: LinkProps) => {
  const locate = useContext(LocateContext);
  const paragraph = /^#paragraph-(p\d+)$/.exec(href || '');
  if (paragraph) return <button type="button" className="lv-memo-ref" onClick={() => locate(paragraph[1])}>{children}</button>;
  const external = /^https?:\/\//i.test(href || '');
  return <a href={href} {...(external ? { target: '_blank', rel: 'noreferrer noopener' } : {})} {...rest}>{children}</a>;
};

const COMPONENTS: Components = { a: MemoLink };
const PLUGINS = [remarkGfm];

/** The model's markdown, rendered without raw HTML; paragraph numbers link to the text when onLocate is given. */
export function MemoText({ text, blockIds, onLocate }: { text: string; blockIds?: Set<string>; onLocate?: (blockId: string) => void }) {
  const body = blockIds && onLocate ? linkParagraphs(text, blockIds) : text;
  return <LocateContext.Provider value={onLocate || (() => undefined)}>
    <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>{body}</ReactMarkdown>
  </LocateContext.Provider>;
}

/** The review memo the model wrote after reading the whole contract, as a chat app would show it. */
export function ReviewMemo({ review, blocks, onLocate }: { review: Review; blocks: Block[]; onLocate: (blockId: string) => void }) {
  const { tx } = useI18n();
  const ids = useMemo(() => new Set(blocks.map(b => b.id)), [blocks]);
  return <div className="lv-rail-body lv-memo">
    <p className="lv-hint">{tx('模型通读全文后写出的审查意见书，未经独立复核。逐条修改在“批注”中处理，修订稿已写入正文。',
      'The review memo the model wrote after reading the whole contract; it has not been independently verified. Work through each edit under Notes; the revised draft is already in the text.')}</p>
    <article className="lv-memo-text" lang="zh-CN"><MemoText text={review.memo || ''} blockIds={ids} onLocate={onLocate} /></article>
  </div>;
}
