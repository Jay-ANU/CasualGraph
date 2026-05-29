import React, { useRef, useState } from 'react';
import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from 'framer-motion';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Database,
  Download,
  FileCheck2,
  FileSearch,
  Github,
  MessageSquare,
  PlayCircle,
  ScreenShare,
  Search,
} from 'lucide-react';
import { githubRepositoryUrl } from '../config/downloads';

const tutorialVideoUrl = 'https://youtu.be/62L-VOsRu8U';

const scrollFeatures = [
  {
    id: 'upload',
    index: '01',
    title: 'Reports become a working memory.',
    shortTitle: 'Upload',
    description: 'Bring ESG disclosures, annual reports, screenshots, and notes into one workspace with source boundaries intact.',
    icon: FileSearch,
    prompt: 'Index Apple, Coca-Cola, and Costco sustainability reports.',
    stats: [['3', 'reports'], ['482', 'chunks'], ['86', 'entities']],
  },
  {
    id: 'ask',
    index: '02',
    title: 'Questions become evidence routes.',
    shortTitle: 'Ask',
    description: 'Ask across documents while the product narrows retrieval through graph context before synthesis.',
    icon: MessageSquare,
    prompt: 'Which Scope 3 categories are reported, missing, or material?',
    stats: [['9', 'sources'], ['24', 'nodes'], ['5', 'steps']],
  },
  {
    id: 'inspect',
    index: '03',
    title: 'Answers stay inspectable.',
    shortTitle: 'Inspect',
    description: 'Citations, chunks, graph nodes, and agent reasoning stay close enough to audit before the answer is reused.',
    icon: FileCheck2,
    prompt: 'Verify every statement before drafting the final paragraph.',
    stats: [['6', 'cited'], ['3', 'gaps'], ['1', 'replan']],
  },
  {
    id: 'write',
    index: '04',
    title: 'Evidence turns into work.',
    shortTitle: 'Write',
    description: 'Draft report paragraphs, compare companies, and refine claims without losing the trail back to source material.',
    icon: BookOpenCheck,
    prompt: 'Rewrite the claim so unsupported financial impact is marked clearly.',
    stats: [['2', 'drafts'], ['4', 'checks'], ['0', 'hidden claims']],
  },
];

const lensCards = [
  {
    title: 'Environment',
    label: 'E',
    detail: 'Emissions, energy, climate risk, water, waste.',
    color: '#34d399',
    rgb: '52 211 153',
  },
  {
    title: 'Social',
    label: 'S',
    detail: 'Workforce, safety, diversity, suppliers, community.',
    color: '#60a5fa',
    rgb: '96 165 250',
  },
  {
    title: 'Governance',
    label: 'G',
    detail: 'Board oversight, controls, ethics, compliance, risk.',
    color: '#f59e0b',
    rgb: '245 158 11',
  },
];

const heroMarqueeWords = Array.from({ length: 8 }, (_, index) => (
  index % 2 === 0 ? 'CausalGraph AI' : 'CausalGraph'
));

const updateSurfaceSpotlight = (event: React.MouseEvent<HTMLElement>) => {
  const rect = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty('--spotlight-x', `${event.clientX - rect.left}px`);
  event.currentTarget.style.setProperty('--spotlight-y', `${event.clientY - rect.top}px`);
};

const ProductFrame = React.memo<{ activeFeature: typeof scrollFeatures[number] }>(({ activeFeature }) => (
  <motion.div
    key={activeFeature.id}
    initial={{ opacity: 0, y: 18, scale: 0.985 }}
    animate={{ opacity: 1, y: 0, scale: 1 }}
    transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
    className="moon-product-frame moon-interactive-surface"
    onMouseMove={updateSurfaceSpotlight}
  >
    <div className="flex items-center justify-between border-b moon-hairline px-5 py-4">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-white/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/[0.24]" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/[0.16]" />
      </div>
      <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] moon-muted">
        Research Desk
      </span>
    </div>

    <div className="grid min-h-[430px] lg:grid-cols-[190px_minmax(0,1fr)]">
      <aside className="hidden border-r moon-hairline bg-white/[0.025] p-4 lg:block">
        <div className="mb-5 flex items-center gap-2 text-[12px] font-semibold text-white/[0.82]">
          <Database className="h-4 w-4" />
          Knowledge base
        </div>
        {['Apple ESG Report', 'Coca-Cola Strategy', 'Costco Sustainability'].map((item, index) => (
          <div
            key={item}
            className={`mb-2 rounded-xl border px-3 py-3 text-[12px] leading-5 ${
              index === 0
                ? 'border-white/[0.18] bg-white/[0.065] text-white'
                : 'border-white/[0.08] text-white/[0.48]'
            }`}
          >
            {item}
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-white/[0.32]">
              {index === 0 ? 'selected' : 'indexed'}
            </div>
          </div>
        ))}
      </aside>

      <div className="min-w-0 p-4 sm:p-5">
        <div className="mb-5 flex flex-wrap items-center gap-2">
          {lensCards.map((domain) => (
            <span key={domain.label} className="moon-pill px-3 py-1 text-[12px] font-semibold">
              <span className="h-2 w-2 rounded-full" style={{ background: domain.color }} />
              {domain.title}
            </span>
          ))}
        </div>

        <div className="ml-auto w-fit max-w-[88%] rounded-2xl rounded-br-md bg-white px-4 py-3 text-[13px] leading-5 text-[#050505]">
          {activeFeature.prompt}
        </div>

        <div className="mt-6 grid gap-5 border-l moon-hairline pl-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 text-[12px] font-semibold text-white/[0.82]">
              <BrainCircuit className="h-4 w-4" />
              {activeFeature.title}
            </div>
            <p className="text-[14px] leading-6 text-white/[0.68]">{activeFeature.description}</p>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {activeFeature.stats.map(([value, label]) => (
              <div key={label} className="moon-stat py-3">
                <div className="font-display text-[32px] font-semibold leading-none text-white">{value}</div>
                <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/[0.38]">{label}</div>
              </div>
            ))}
          </div>

          <div className="moon-panel-soft rounded-2xl p-4">
            <div className="mb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-white/[0.38]">
              Evidence rule
            </div>
            <p className="text-[13px] leading-6 text-white/[0.62]">
              Use the answer only when every important claim can be traced to a source or marked as a gap.
            </p>
          </div>
        </div>
      </div>
    </div>
  </motion.div>
));

ProductFrame.displayName = 'ProductFrame';

const Home: React.FC = () => {
  const navigate = useNavigate();
  const heroRef = useRef<HTMLDivElement>(null);
  const shouldReduceMotion = useReducedMotion();
  const [heroPrompt, setHeroPrompt] = useState('');
  const heroCursorX = useMotionValue(42);
  const heroCursorY = useMotionValue(42);
  const heroDriftX = useMotionValue(0);
  const heroDriftY = useMotionValue(0);

  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ['start start', 'end start'],
  });
  const heroMarqueeScrollX = useTransform(scrollYProgress, [0, 1], [0, -160]);
  const heroMoonY = useTransform(scrollYProgress, [0, 1], [0, -56]);
  const heroMoonScale = useTransform(scrollYProgress, [0, 1], [1, 0.86]);
  const heroContentY = useTransform(scrollYProgress, [0, 1], [0, -42]);
  const heroContentOpacity = useTransform(scrollYProgress, [0, 0.78], [1, 0.3]);
  const heroCursorSpringX = useSpring(heroCursorX, { stiffness: 420, damping: 34, mass: 0.6 });
  const heroCursorSpringY = useSpring(heroCursorY, { stiffness: 420, damping: 34, mass: 0.6 });
  const heroMarqueeMouseX = useSpring(heroDriftX, { stiffness: 120, damping: 26, mass: 0.8 });
  const heroMoonMouseX = useTransform(heroMarqueeMouseX, (value) => value * 0.16);
  const heroMoonMouseY = useSpring(heroDriftY, { stiffness: 130, damping: 28, mass: 0.8 });

  const updateHeroPointer = (event: React.MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const normalizedX = (x / rect.width - 0.5) * 2;
    const normalizedY = (y / rect.height - 0.5) * 2;

    heroCursorX.set(x - 14);
    heroCursorY.set(y - 14);
    heroDriftX.set(normalizedX * 82);
    heroDriftY.set(normalizedY * 20);
    event.currentTarget.style.setProperty('--hero-pointer-x', `${x}px`);
    event.currentTarget.style.setProperty('--hero-pointer-y', `${y}px`);
  };

  const handleHeroSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = heroPrompt.trim();
    navigate(prompt ? `/agent?prompt=${encodeURIComponent(prompt)}` : '/agent');
  };

  return (
    <div className="moon-page overflow-x-hidden">
      <section ref={heroRef} className="moon-hero border-b moon-hairline" onMouseMove={updateHeroPointer}>
        <motion.div
          aria-hidden="true"
          className="moon-hero-marquee-layer"
          style={{ x: shouldReduceMotion ? 0 : heroMarqueeScrollX }}
        >
          <motion.div className="moon-hero-marquee-mouse" style={{ x: shouldReduceMotion ? 0 : heroMarqueeMouseX }}>
            <div className="moon-hero-marquee">
              {heroMarqueeWords.map((word, index) => (
                <span key={`${word}-${index}`}>{word}</span>
              ))}
            </div>
          </motion.div>
        </motion.div>
        <motion.div
          aria-hidden="true"
          className="moon-eclipse-layer"
          style={{
            y: shouldReduceMotion ? 0 : heroMoonY,
            scale: shouldReduceMotion ? 1 : heroMoonScale,
          }}
        >
          <motion.div
            className="moon-eclipse"
            style={{
              x: shouldReduceMotion ? 0 : heroMoonMouseX,
              y: shouldReduceMotion ? 0 : heroMoonMouseY,
            }}
          />
        </motion.div>
        <motion.div
          className="moon-hero-cursor"
          aria-hidden="true"
          style={{
            x: shouldReduceMotion ? 42 : heroCursorSpringX,
            y: shouldReduceMotion ? 42 : heroCursorSpringY,
          }}
        />
        <div className="moon-pointer-glow" aria-hidden="true" />
        <div className="moon-scanline" />

        <motion.div
          style={{ y: heroContentY, opacity: heroContentOpacity }}
          className="moon-hero-content relative z-10 mx-auto flex max-w-page-wide flex-col items-center px-4 text-center sm:px-6 lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16"
        >
          <h1 className="sr-only">CausalGraph AI evidence graph research assistant</h1>
          <p className="moon-hero-line max-w-2xl">
            Trace evidence into defensible answers
          </p>

          <form
            onSubmit={handleHeroSubmit}
            className="moon-composer moon-hero-composer moon-interactive-surface mt-8 w-full max-w-2xl p-3 text-left"
            onMouseMove={updateSurfaceSpotlight}
          >
            <div className="flex min-h-[62px] items-start gap-3 px-3 py-3">
              <Search className="mt-1 h-4 w-4 shrink-0 text-white/[0.38]" />
              <input
                value={heroPrompt}
                onChange={(event) => setHeroPrompt(event.target.value)}
                className="min-w-0 flex-1 border-0 bg-transparent text-[15px] leading-6 text-white/[0.82] outline-none placeholder:text-white/[0.42]"
                placeholder="Ask a difficult question across your reports..."
                aria-label="Ask CausalGraph"
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t moon-hairline px-3 pt-3">
              <div className="flex items-center gap-2 text-[12px] moon-muted">
                <span className="moon-pill px-2.5 py-1">All reports</span>
                <span className="hidden sm:inline">agent verifies before writing</span>
              </div>
              <button type="submit" className="moon-btn-primary !px-4 !py-2">
                Open desk
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </form>

        </motion.div>
      </section>

      <section className="moon-section moon-scroll-story border-b moon-hairline">
        <div className="mx-auto max-w-page-wide px-4 sm:px-6 lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          {scrollFeatures.map((feature) => (
            <motion.article
              key={feature.id}
              viewport={{ amount: 0.42 }}
              initial={{ opacity: 0, y: 46 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              className="moon-story-panel grid gap-10 pb-14 pt-28 lg:grid-cols-[0.72fr_1.28fr] lg:items-center xl:gap-16"
            >
              <div>
                <div className="moon-scroll-rail mb-8">
                  {scrollFeatures.map((railFeature) => {
                    const Icon = railFeature.icon;
                    const active = railFeature.id === feature.id;
                    return (
                      <div
                        key={railFeature.id}
                        className={`moon-rail-item ${active ? 'is-active' : ''}`}
                      >
                        <span>{railFeature.index}</span>
                        <Icon className="h-4 w-4" />
                        <strong>{railFeature.shortTitle}</strong>
                      </div>
                    );
                  })}
                </div>

                <h2 className="font-display text-[42px] font-semibold leading-tight text-white lg:text-[56px]">
                  {feature.title}
                </h2>
                <p className="mt-5 max-w-xl text-[16px] leading-7 moon-copy">{feature.description}</p>
                <Link to="/agent" className="moon-btn-secondary mt-7">
                  Start a run
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>

              <ProductFrame activeFeature={feature} />
            </motion.article>
          ))}
        </div>
      </section>

      <section className="moon-deferred-section border-t moon-hairline">
        <div className="mx-auto grid max-w-page-wide gap-4 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16">
          <div className="moon-panel moon-interactive-surface rounded-[28px] p-6" onMouseMove={updateSurfaceSpotlight}>
            <Github className="mb-8 h-8 w-8 text-white/[0.72]" />
            <h2 className="text-[30px] font-semibold tracking-normal text-white">Open source by default.</h2>
            <p className="mt-3 text-[15px] leading-7 moon-copy">
              The public repository contains the app code and templates. Private keys, indexes, and uploaded documents stay outside the repository.
            </p>
            <a href={githubRepositoryUrl} target="_blank" rel="noreferrer" className="moon-btn-secondary mt-7">
              View GitHub
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>

          <div className="moon-panel moon-interactive-surface rounded-[28px] p-6" onMouseMove={updateSurfaceSpotlight}>
            <ScreenShare className="mb-8 h-8 w-8 text-white/[0.72]" />
            <h2 className="text-[30px] font-semibold tracking-normal text-white">Desktop companion for active work.</h2>
            <p className="mt-3 text-[15px] leading-7 moon-copy">
              Drop reports, summarize screens, review drafts, and continue asking when your research context changes.
            </p>
            <Link to="/desktop" className="moon-btn-primary mt-7">
              Download desktop
              <Download className="h-4 w-4" />
            </Link>
          </div>

          <a
            href={tutorialVideoUrl}
            target="_blank"
            rel="noreferrer"
            className="moon-panel moon-interactive-surface group flex items-center justify-between gap-4 rounded-[28px] px-5 py-4 transition-colors hover:border-white/[0.18] lg:col-span-2"
            onMouseMove={updateSurfaceSpotlight}
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/[0.12] bg-white/[0.06] text-white/[0.78]">
                <PlayCircle className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block text-[15px] font-semibold text-white">Tutorial video</span>
                <span className="block truncate text-[12px] moon-muted">YouTube</span>
              </span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-white/[0.64] transition-transform group-hover:translate-x-0.5" />
          </a>
        </div>
      </section>
    </div>
  );
};

export default Home;
