import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Camera,
  Download,
  FileText,
  FolderOpen,
  MessageSquare,
  Settings,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react';
import { desktopMacArm64DownloadUrl, desktopReleaseNotesUrl } from '../config/downloads';

const downloadDetails = [
  ['Version', '0.1.0 beta'],
  ['Platform', 'macOS Apple Silicon'],
  ['Package', 'CausalGraph-Pet-0.1.0-mac-arm64.zip'],
  ['Signature', 'Unsigned beta build'],
];

const installSteps = [
  'Download the macOS Apple Silicon zip.',
  'Move CausalGraph Pet into Applications.',
  'Control-click Open for the first unsigned beta launch.',
  'Sign in with the same CausalGraph account used on web.',
];

const sidebarItems: Array<[string, React.ElementType]> = [
  ['New session', MessageSquare],
  ['Sessions', FolderOpen],
  ['Evidence', FileText],
  ['Settings', Settings],
];

const fileRows = [
  ['CSR 2024 Full Report.pdf', 'Indexed just now'],
  ['Supplier Code of Conduct.pdf', 'Ready for evidence search'],
  ['Screenshot capture', 'Summary attached'],
];

const DesktopPetWindow: React.FC = () => (
  <div className="moon-device-shell" aria-label="CausalGraph Pet desktop app mockup">
    <div className="moon-device-screen">
      <div className="moon-app-window">
        <aside className="moon-app-sidebar">
          <div className="flex items-center gap-3 border-b border-white/[0.08] pb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-black">
              <MessageSquare className="h-4 w-4" />
            </div>
            <div>
              <div className="text-[13px] font-semibold text-white">CausalGraph Pet</div>
              <div className="mt-0.5 font-mono text-[10px] text-white/38">v0.1.0 beta</div>
            </div>
          </div>

          <nav className="mt-5 space-y-1">
            {sidebarItems.map(([label, Icon], index) => (
              <div key={label} className={`moon-app-nav-row ${index === 0 ? 'is-active' : ''}`}>
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </div>
            ))}
          </nav>

          <div className="mt-auto rounded-[16px] border border-white/[0.08] bg-white/[0.035] p-3">
            <div className="text-[12px] font-semibold text-white">Synced workspace</div>
            <div className="mt-1 text-[11px] text-white/38">jay@causalgraph.ai</div>
          </div>
        </aside>

        <main className="moon-app-main">
          <div className="moon-app-topbar">
            <div>
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-white/34">Desktop capture</div>
              <div className="mt-1 text-[18px] font-semibold text-white">Research intake</div>
            </div>
            <button type="button" className="moon-app-icon-button" aria-label="Capture screenshot">
              <Camera className="h-4 w-4" />
            </button>
          </div>

          <div className="moon-pet-dropzone">
            <UploadCloud className="h-8 w-8 text-white" />
            <div>
              <div className="text-[15px] font-semibold text-white">Drop reports here</div>
              <div className="mt-1 text-[12px] text-white/42">PDFs, notes, screenshots, and disclosure excerpts</div>
            </div>
            <button type="button">Capture screenshot</button>
          </div>

          <div className="moon-pet-filelist">
            {fileRows.map(([name, status]) => (
              <div key={name} className="moon-pet-file-row">
                <FileText className="h-4 w-4" />
                <div>
                  <strong>{name}</strong>
                  <span>{status}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="moon-pet-thread">
            <div className="moon-thread-bubble user">What changed in the latest report?</div>
            <div className="moon-thread-bubble assistant">
              I found three evidence-backed updates and attached the source chunks for review.
            </div>
            <div className="moon-pet-composer">
              <SearchDot />
              <span>Ask about this workspace...</span>
              <button type="button"><ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        </main>
      </div>
    </div>
    <div className="moon-device-base" />
  </div>
);

const SearchDot: React.FC = () => (
  <span className="relative flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-white/38">
    <span className="h-1 w-1 rounded-full bg-white/72" />
  </span>
);

const DesktopDownload: React.FC = () => (
  <div className="moon-page overflow-x-hidden">
    <section className="moon-section moon-desktop-hero border-b moon-hairline">
      <div className="relative z-10 mx-auto grid min-h-[560px] max-w-page-2xl gap-10 px-4 py-10 sm:px-6 lg:min-h-[580px] lg:grid-cols-[0.78fr_1.22fr] lg:items-center lg:px-8 xl:px-12 2xl:px-16">
        <div className="max-w-[520px]">
          <div className="mb-7 font-mono text-[11px] font-semibold uppercase tracking-[0.24em] text-white/42">Desktop</div>
          <h1 className="font-display text-[54px] font-semibold leading-[0.95] text-white sm:text-[68px] xl:text-[82px]">
            CausalGraph Pet
          </h1>
          <p className="mt-6 text-[18px] leading-8 moon-copy">
            Drop reports, capture screens, and keep evidence work beside your research.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a href={desktopMacArm64DownloadUrl} className="moon-btn-primary" download>
              <Download className="h-4 w-4" />
              Download for macOS
            </a>
            <a href={desktopReleaseNotesUrl} className="moon-btn-secondary">
              Release notes
            </a>
          </div>
          <div className="mt-5 flex items-start gap-3 rounded-[18px] border border-white/[0.10] bg-white/[0.045] p-4 text-[13px] leading-6 text-white/52">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-white/70" />
            Current build is a private beta for Apple Silicon macOS. The app is unsigned, so first launch requires Control-click Open.
          </div>
        </div>

        <DesktopPetWindow />
      </div>
    </section>

    <section className="mx-auto max-w-page-2xl px-4 py-12 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
      <div className="moon-release-panel">
        <div className="moon-release-identity">
          <div className="moon-release-mark">CG</div>
          <div>
            <div className="text-[20px] font-semibold text-white">CausalGraph Pet</div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-[0.16em] text-white/34">Version 0.1.0 beta</div>
          </div>
        </div>

        <div className="moon-release-grid">
          {downloadDetails.map(([label, value]) => (
            <div key={label} className="moon-release-cell">
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        <div className="moon-install-steps">
          <div>
            <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-white/38">How to install</div>
            <ol className="mt-4 space-y-3">
              {installSteps.map((step, index) => (
                <li key={step}>
                  <span>{index + 1}</span>
                  <p>{step}</p>
                </li>
              ))}
            </ol>
          </div>
          <Link to="/agent" className="moon-btn-secondary mt-6 w-fit">
            Open web agent
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  </div>
);

export default DesktopDownload;
