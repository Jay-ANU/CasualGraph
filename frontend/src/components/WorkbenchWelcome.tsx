import React from 'react';
import { ArrowRight, FileUp } from 'lucide-react';
import { useI18n } from '../i18n/core';

type Starter = { title: string; prompt: string; tier: 'flash' | 'deep' };

interface Props {
  documentCount: number;
  starters: Starter[];
  composer: React.ReactNode;
  onUpload: () => void;
  onLibrary: () => void;
  onPrompt: (starter: Starter) => void;
}

/** Empty state of the research desk: greeting, the composer, and a few ways in. */
export default function WorkbenchWelcome({ documentCount, starters, composer, onUpload, onLibrary, onPrompt }: Props) {
  const { tx } = useI18n();
  return (
    <div className="research-welcome mx-auto flex min-h-full w-full max-w-[760px] flex-col justify-center px-4 pb-12 pt-10 sm:px-6">
      <h2 className="display text-center text-[30px] leading-tight sm:text-display-md">{tx('今天想研究什么？', 'What would you like to research?')}</h2>
      <p className="mt-3 text-center text-sm text-ink-3">
        <span>
          {documentCount > 0
            ? tx(`文档库中有 ${documentCount} 份文档`, `${documentCount} document${documentCount === 1 ? '' : 's'} in your library`)
            : tx('从一份文档开始，或直接提出通用问题', 'Start with a document, or ask a general question')}
        </span>
        <span aria-hidden="true" className="mx-2 text-ink-5">·</span>
        <button type="button" onClick={onLibrary} className="text-link text-ink-2">
          {tx('查看文档库', 'View library')}
        </button>
      </p>

      <div className="mt-7">{composer}</div>

      <div className="research-starters mt-8 grid gap-2 sm:grid-cols-3">
        {starters.slice(0, 3).map((starter) => (
          <button
            key={starter.title}
            type="button"
            onClick={() => onPrompt(starter)}
            className="rounded-xl border border-line bg-white/60 px-3.5 py-3 text-left transition-colors hover:border-line-strong hover:bg-white"
          >
            <span className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-ink">{starter.title}</span>
              <span className="text-[11px] text-ink-4">{starter.tier === 'deep' ? tx('深度', 'Deep') : tx('快速', 'Fast')}</span>
            </span>
            <span className="mt-1 line-clamp-2 block text-[13px] leading-5 text-ink-3">{starter.prompt}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={onUpload}
        className="mt-2 flex w-full items-center gap-3 rounded-xl border border-dashed border-line-strong px-3.5 py-3 text-left transition-colors hover:border-ink-5 hover:bg-white"
      >
        <FileUp className="h-4 w-4 shrink-0 text-ink-4" />
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-medium text-ink">{tx('使用自己的资料', 'Bring your own evidence')}</span>
          <span className="block text-[13px] text-ink-3">{tx('上传一份合同，围绕它提问。', 'Upload a contract and ask questions about it.')}</span>
        </span>
        <ArrowRight className="h-4 w-4 shrink-0 text-ink-4" />
      </button>
    </div>
  );
}
