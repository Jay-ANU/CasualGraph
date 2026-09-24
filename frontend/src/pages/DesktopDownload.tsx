import React from 'react';
import { Link } from 'react-router-dom';
import { Download } from 'lucide-react';
import { desktopMacArm64DownloadUrl, desktopReleaseNotesUrl } from '../config/downloads';
import useDocumentTitle from '../utils/useDocumentTitle';

const RELEASE_DETAILS = [
  ['Version', '0.1.0 beta'],
  ['Requires', 'A Mac with Apple silicon'],
  ['File', 'CausalGraph-Pet-0.1.0-mac-arm64.zip'],
  ['Signing', 'Not yet signed or notarised'],
];

const INSTALL_STEPS = [
  'Download the zip file and open it.',
  'Move CausalGraph Pet to your Applications folder.',
  'The first time, Control-click the app and choose Open. macOS asks because this beta is not signed yet.',
  'Sign in with the account you use for CausalGraph on the web.',
];

const DesktopDownload: React.FC = () => {
  useDocumentTitle('CausalGraph Pet for Mac');
  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-14 sm:px-8 sm:pt-20">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-16">
        <div>
          <h1 className="display text-[40px] leading-[1.06] sm:text-display-lg">CausalGraph Pet for Mac</h1>
          <p className="mt-5 max-w-md text-[17px] leading-relaxed text-ink-3">
            A small assistant that sits at the edge of your screen. Drop a report or a screenshot on it and ask about it,
            without switching to the browser.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href={desktopMacArm64DownloadUrl} className="btn btn-primary btn-lg" download>
              <Download className="h-4 w-4" />
              Download for macOS
            </a>
            <a href={desktopReleaseNotesUrl} className="btn btn-secondary btn-lg" target="_blank" rel="noreferrer">
              Release notes
            </a>
          </div>
          <p className="mt-4 text-sm text-ink-4">Beta 0.1.0 · Apple silicon</p>
        </div>

        <figure className="m-0">
          <picture>
            <source srcSet="/assets/desktop-pet-hero-mockup.webp" type="image/webp" />
            <img
              src="/assets/desktop-pet-hero-mockup.png"
              alt="CausalGraph Pet open on a Mac desktop, with an area to drop a report and a reply to a question"
              width={1536}
              height={1024}
              className="h-auto w-full rounded-xl border border-line"
            />
          </picture>
        </figure>
      </div>

      <div className="mt-20 grid gap-12 border-t border-line pt-12 md:grid-cols-2 md:gap-16">
        <section>
          <h2 className="text-lg font-medium text-ink">Install</h2>
          <ol className="mt-5 space-y-4">
            {INSTALL_STEPS.map((step, index) => (
              <li key={step} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2 leading-relaxed text-ink-2">
                <span className="font-mono text-sm leading-[1.65rem] text-ink-4">{index + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="text-lg font-medium text-ink">Details</h2>
          <dl className="mt-5 divide-y divide-line border-y border-line">
            {RELEASE_DETAILS.map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-6 py-3 text-sm">
                <dt className="shrink-0 text-ink-4">{label}</dt>
                <dd className="min-w-0 truncate text-right text-ink-2">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-6 text-sm leading-relaxed text-ink-3">
            Prefer the browser?{' '}
            <Link to="/agent" className="text-link text-ink">
              Open the research desk
            </Link>{' '}
            — it uses the same account and library.
          </p>
        </section>
      </div>
    </div>
  );
};

export default DesktopDownload;
