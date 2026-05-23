import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Download,
  FileUp,
  MessageSquare,
  ScreenShare,
} from 'lucide-react';
import { desktopMacArm64DownloadUrl, desktopReleaseNotesUrl } from '../config/downloads';

const downloadDetails = [
  ['Version', '0.1.0 beta'],
  ['Download', 'CausalGraph-Pet-0.1.0-mac-arm64.zip'],
  ['Platform', 'macOS Apple Silicon'],
  ['Release', 'GitHub Release'],
  ['Signature', 'Unsigned beta build'],
];

const workflows = [
  {
    icon: FileUp,
    title: 'Drop reports',
    description: 'Drag PDFs, filings, or notes onto the desktop companion and send them into your private knowledge base.',
  },
  {
    icon: ScreenShare,
    title: 'Capture screen',
    description: 'Summarize visible work, documents, or error states without switching context or copying text.',
  },
  {
    icon: MessageSquare,
    title: 'Continue asking',
    description: 'Ask follow-up questions with the same account, model routing, evidence retrieval, and memory behavior as the web agent.',
  },
];

const installNotes = [
  {
    title: 'Control-click Open',
    description: 'The current beta is not signed yet. After download, Control-click the app in Finder and choose Open.',
    meta: 'macOS security',
  },
  {
    title: 'Allow screen capture',
    description: 'macOS may ask for Screen Recording permission before screenshot summaries can work.',
    meta: 'System Settings',
  },
  {
    title: 'Use your web account',
    description: 'Sign in with the same CausalGraph account so uploaded documents and conversations stay in sync.',
    meta: 'Same workspace',
  },
];

const releaseHighlights = [
  {
    title: 'Desktop companion window',
    description: 'Open a small assistant surface from the desktop and keep report work close to the current task.',
  },
  {
    title: 'Report drop upload',
    description: 'Send PDFs and notes into the same private knowledge base used by the web agent.',
  },
  {
    title: 'Screen summary flow',
    description: 'Capture visible context, summarize what matters, and continue the conversation from the app.',
  },
];

const ProductMockup: React.FC = () => (
  <figure className="w-full min-w-0 max-w-[520px] justify-self-center lg:max-w-[620px] lg:justify-self-end">
    <img
      src="/assets/desktop-pet-hero-mockup.png"
      alt="CausalGraph Pet desktop assistant preview"
      className="block w-full rounded-2xl"
      loading="eager"
    />
  </figure>
);

const DesktopDownload: React.FC = () => {
  const [activeInfoTab, setActiveInfoTab] = useState<'download' | 'install' | 'release'>('download');

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas text-ink">
      <section className="border-b border-hairline-soft bg-canvas">
        <div className="mx-auto grid max-w-[1280px] gap-8 px-4 py-8 sm:px-6 md:grid-cols-[minmax(0,280px)_minmax(380px,520px)] md:items-center md:justify-center md:py-10 lg:grid-cols-[minmax(0,390px)_minmax(520px,620px)] lg:px-8 xl:gap-12">
          <div className="min-w-0">
            <h1 className="font-display text-[40px] font-semibold leading-[1.04] tracking-normal text-ink md:whitespace-nowrap md:text-[32px] lg:text-[46px] xl:text-[52px]">
              CausalGraph Pet
            </h1>
            <p className="mt-5 max-w-[390px] text-[16px] leading-7 text-ink-steel sm:text-[17px]">
              A desktop companion for report drops, screen summaries, and follow-up research without switching back to the browser.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <a
                href={desktopMacArm64DownloadUrl}
                className="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-md bg-ink px-4 py-3 text-[13px] font-semibold leading-none text-white transition hover:bg-ink-charcoal sm:w-auto lg:px-5 lg:text-[14px]"
                download
              >
                <Download className="h-4 w-4" />
                Download for macOS
              </a>
              <a
                href={desktopReleaseNotesUrl}
                className="inline-flex w-full items-center justify-center whitespace-nowrap rounded-md border border-hairline bg-white px-4 py-3 text-[13px] font-semibold leading-none text-ink transition hover:border-ink sm:w-auto lg:px-5 lg:text-[14px]"
              >
                Release notes
              </a>
            </div>
          </div>

          <ProductMockup />
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 py-12 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
        <div className="rounded-2xl border border-hairline bg-white p-4 lg:p-5">
          <div className="flex flex-col gap-3 border-b border-hairline pb-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-[26px] font-semibold tracking-normal text-ink">Release information</h2>
              <p className="mt-1 text-[14px] leading-6 text-ink-steel">Download, install notes, and release highlights in one place.</p>
            </div>
            <div className="inline-flex rounded-full border border-hairline bg-surface-soft p-1">
              {[
                ['download', 'Download'],
                ['install', 'Install'],
                ['release', 'New'],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveInfoTab(id as 'download' | 'install' | 'release')}
                  className={`rounded-full px-4 py-2 text-[13px] font-semibold transition ${
                    activeInfoTab === id ? 'bg-ink text-white' : 'text-ink-steel hover:bg-white hover:text-ink'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5">
            {activeInfoTab === 'download' && (
              <div className="grid gap-3">
                {downloadDetails.map(([label, value]) => (
                  <div key={label} className="grid gap-1 rounded-lg bg-surface-soft px-4 py-3 sm:grid-cols-[150px_1fr] sm:gap-4">
                    <div className="text-[13px] font-semibold text-ink">{label}</div>
                    <div className="break-words text-[13px] leading-5 text-ink-steel">{value}</div>
                  </div>
                ))}
              </div>
            )}

            {activeInfoTab === 'install' && (
              <div className="grid gap-3 lg:grid-cols-3">
                {installNotes.map((item, index) => (
                  <div key={item.title} className="rounded-xl bg-surface-soft p-5">
                    <div className="mb-4 flex items-center gap-3">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ink text-[12px] font-semibold text-white">
                        {index + 1}
                      </span>
                      <h3 className="text-[16px] font-semibold text-ink">{item.title}</h3>
                    </div>
                    <p className="text-[14px] leading-6 text-ink-steel">{item.description}</p>
                  </div>
                ))}
              </div>
            )}

            {activeInfoTab === 'release' && (
              <div className="grid gap-0 border-y border-hairline lg:grid-cols-3">
                {releaseHighlights.map((item, index) => (
                  <div
                    key={item.title}
                    className={`py-6 ${index > 0 ? 'border-t border-hairline lg:border-l lg:border-t-0 lg:pl-8' : ''} ${
                      index < releaseHighlights.length - 1 ? 'lg:pr-8' : ''
                    }`}
                  >
                    <h3 className="text-[18px] font-semibold tracking-normal text-ink">{item.title}</h3>
                    <p className="mt-3 text-[14px] leading-6 text-ink-steel">{item.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="border-y border-hairline-soft bg-canvas">
        <div className="mx-auto max-w-page-wide px-4 py-14 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
          <div className="mb-8 max-w-2xl">
            <h2 className="text-heading-lg tracking-normal lg:text-[52px]">How CausalGraph Pet works</h2>
            <p className="mt-3 text-[16px] leading-7 text-ink-steel">
              The desktop app keeps the same evidence-first workflow available at the edge of your screen.
            </p>
          </div>

          <div className="grid gap-8 lg:grid-cols-3 lg:gap-0">
            {workflows.map((item, index) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.title}
                  className={`${
                    index > 0 ? 'border-t border-hairline pt-8 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0' : ''
                  } ${index < workflows.length - 1 ? 'lg:pr-8' : ''}`}
                >
                  <div className="mb-7 flex items-start justify-between">
                    <Icon className="h-11 w-11 text-ink" />
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ink text-[12px] font-semibold text-white">
                      {index + 1}
                    </span>
                  </div>
                  <h3 className="text-[22px] font-semibold tracking-normal text-ink">{item.title}</h3>
                  <p className="mt-3 text-[14px] leading-6 text-ink-steel">{item.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page-wide px-4 pb-16 sm:px-6 lg:px-8 xl:max-w-page-xl 2xl:max-w-page-2xl">
        <div className="overflow-hidden rounded-2xl bg-ink p-8 text-white sm:p-10 lg:flex lg:items-center lg:justify-between lg:gap-10">
          <div className="max-w-3xl">
            <h2 className="font-display text-[38px] font-semibold leading-tight tracking-normal text-white sm:text-[48px]">
              Work with CausalGraph beside your research.
            </h2>
            <p className="mt-4 max-w-xl text-[16px] leading-7 text-white/70">
              Keep analysis, notes, documents, and evidence-grounded answers within reach.
            </p>
          </div>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row lg:mt-0">
            <a href={desktopMacArm64DownloadUrl} className="cg-btn-tertiary w-full justify-center sm:w-auto" download>
              <Download className="h-4 w-4" />
              Download Desktop
            </a>
            <Link to="/agent" className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-white/30 px-6 py-3 text-[14px] font-semibold text-white transition hover:bg-white/10 sm:w-auto">
              Open Agent
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

    </div>
  );
};

export default DesktopDownload;
