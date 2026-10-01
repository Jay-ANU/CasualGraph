import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, ChevronDown, Pause, Play } from 'lucide-react';
import { Link } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import LanguageSwitch from '../components/LanguageSwitch';
import { githubRepositoryUrl } from '../config/downloads';
import { useI18n } from '../i18n/core';
import useDocumentTitle from '../utils/useDocumentTitle';
import AgentNetwork from './home/AgentNetwork';
import Capabilities from './home/Capabilities';
import { COPY } from './home/copy';
import CountUp from './home/CountUp';
import HeroVideo from './home/HeroVideo';
import { useReducedMotion, useReveal, useScrollProgress } from './home/motion';
import ScrambleWord from './home/ScrambleWord';
import SparkField from './home/SparkField';
import WorkflowStory from './home/WorkflowStory';
import '@fontsource-variable/inter/wght.css';
import './home/home.css';

const MOTION_KEY = 'causalgraph.home-motion';
const YEAR = new Date().getFullYear();

const savedPause = () => {
  try { if (localStorage.getItem(MOTION_KEY) === 'paused') return true; } catch { /* default */ }
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return Boolean(connection?.saveData);
};

/** Chinese animates per character, English per word, so English never breaks mid-word. */
function Split({ text, lang }: { text: string; lang: 'zh' | 'en' }) {
  const parts = lang === 'zh' ? Array.from(text) : text.split(/(\s+)/);
  let n = 0;
  return <>{parts.map((part, i) => (/^\s+$/.test(part) ? ' ' : <span key={i} className="lp-ch" style={{ '--i': n++ } as React.CSSProperties}>{part}</span>))}</>;
}

/** Headlines carry their own line breaks ("\n") so Chinese never splits mid-phrase. */
function Lines({ text }: { text: string }) {
  const parts = text.split('\n');
  return <>{parts.map((part, i) => <span key={i}>{i > 0 && <br />}{part}</span>)}</>;
}

export default function Home() {
  const { lang } = useI18n();
  const copy = COPY[lang];
  const reduced = useReducedMotion();
  const [paused, setPaused] = useState(savedPause);
  const [heroOnScreen, setHeroOnScreen] = useState(true);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const root = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const statement = useRef<HTMLDivElement>(null);
  const motionOn = !reduced && !paused;
  useDocumentTitle(copy.title);
  useReveal(root, lang);

  // Dark browser chrome on phones while the landing page is open.
  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    const previous = meta?.getAttribute('content');
    meta?.setAttribute('content', '#05050b');
    return () => { if (previous) meta?.setAttribute('content', previous); };
  }, []);

  useEffect(() => {
    const element = hero.current;
    if (!element || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(([entry]) => setHeroOnScreen(entry.isIntersecting), { threshold: 0.02 });
    observer.observe(element);
    const onVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibility);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', onVisibility); };
  }, []);

  // Hero: content lifts and fades, the film pushes in slightly, as the page scrolls away.
  useEffect(() => {
    const element = hero.current;
    if (!element) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const p = Math.min(1, Math.max(0, -element.getBoundingClientRect().top / Math.max(1, element.offsetHeight)));
      element.style.setProperty('--hp', p.toFixed(4));
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', schedule, { passive: true });
    return () => { window.removeEventListener('scroll', schedule); if (frame) cancelAnimationFrame(frame); };
  }, []);

  useScrollProgress(statement, (progress) => {
    statement.current?.style.setProperty('--p', progress.toFixed(4));
  });

  const toggleMotion = () => {
    const next = !paused;
    setPaused(next);
    try { localStorage.setItem(MOTION_KEY, next ? 'paused' : 'playing'); } catch { /* this visit only */ }
  };
  // In-page links glide to their section (and jump straight there when motion is reduced).
  const toSection = (event: React.MouseEvent<HTMLAnchorElement>) => {
    const target = document.getElementById(event.currentTarget.hash.slice(1));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    // Keep the router's own history state; only the fragment changes.
    history.replaceState(history.state, '', event.currentTarget.hash);
  };
  const onHeroPointer = (event: React.PointerEvent<HTMLElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--mx', `${event.clientX - box.left}px`);
    event.currentTarget.style.setProperty('--my', `${event.clientY - box.top}px`);
  };

  const statementWords = lang === 'zh' ? Array.from(copy.statement.text) : copy.statement.text.split(/ |(?=\n)|(?<=\n)/).filter(Boolean);
  const statementCount = statementWords.filter(word => word !== '\n').length;

  return (
    <div ref={root} className={`lp ${motionOn ? '' : 'lp-still'}`} lang={lang === 'zh' ? 'zh-CN' : 'en'}>
      <section ref={hero} className="lp-hero" aria-labelledby="lp-hero-title" onPointerMove={onHeroPointer}>
        <HeroVideo playing={motionOn && heroOnScreen && pageVisible} />
        <div className="lp-hero-shade" aria-hidden="true" />
        <SparkField active={motionOn && heroOnScreen && pageVisible} />
        <div className="lp-hero-grid" aria-hidden="true" />
        <div className="lp-grain" aria-hidden="true" />

        <div className="lp-hero-inner">
          <a href="#agents" className="lp-badge" onClick={toSection}>
            <span className="lp-badge-dot" aria-hidden="true" />
            {copy.hero.badge}
            <ArrowRight size={14} aria-hidden="true" />
          </a>
          <h1 id="lp-hero-title" className="lp-title" key={lang}>
            <span className="sr-only">{copy.hero.line1}{lang === 'en' ? ' ' : ''}{copy.hero.line2}</span>
            <span aria-hidden="true" className="lp-line"><Split text={copy.hero.line1} lang={lang} /></span>
            <span aria-hidden="true" className="lp-line lp-wipe"><span className="lp-gradient-text">{copy.hero.line2}</span></span>
          </h1>
          <p className="lp-reviewing">
            <span className="lp-live-dot" aria-hidden="true" />
            <span>{copy.hero.reviewing}</span>
            <ScrambleWord key={lang} words={copy.hero.words} lang={lang} still={!motionOn} />
            <span className="sr-only">{copy.hero.words.join(lang === 'zh' ? '、' : ', ')}</span>
          </p>
          <p className="lp-sub">{copy.hero.sub}</p>
          <div className="lp-actions">
            <Link to="/legal" className="lp-btn lp-btn-primary">
              <span>{copy.hero.primary}</span>
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <a href="#workflow" className="lp-btn lp-btn-ghost" onClick={toSection}>
              <span className="lp-play" aria-hidden="true"><Play size={12} fill="currentColor" /></span>
              {copy.hero.secondary}
            </a>
          </div>
          <ul className="lp-chips">
            {copy.hero.chips.map(chip => <li key={chip}>{chip}</li>)}
          </ul>
        </div>

        <div className="lp-hero-foot">
          <dl className="lp-stats">
            {copy.hero.stats.map(stat => (
              <div key={stat.label}>
                <dt>{stat.label}</dt>
                <dd><CountUp value={stat.value} still={!motionOn} /></dd>
              </div>
            ))}
          </dl>
          <a href="#scenarios" className="lp-scroll" aria-label={copy.hero.scroll} onClick={toSection}>
            <span>{copy.hero.scroll}</span>
            <ChevronDown size={16} aria-hidden="true" />
          </a>
        </div>
        {/* Outside the footer row: its entrance animation would otherwise anchor the button. */}
        {!reduced && (
          <button type="button" className="lp-motion" onClick={toggleMotion} aria-pressed={paused} aria-label={paused ? copy.hero.play : copy.hero.pause} title={paused ? copy.hero.play : copy.hero.pause}>
            {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
          </button>
        )}
      </section>

      <section id="scenarios" className="lp-section lp-scenarios">
        <header className="lp-head" data-reveal>
          <p className="lp-eyebrow">{copy.scenarios.eyebrow}</p>
          <h2><Lines text={copy.scenarios.title} /></h2>
          <p>{copy.scenarios.sub}</p>
        </header>
        <div className="lp-marquees" aria-hidden="true">
          {[0, 1].map(row => {
            const words = row ? [...copy.hero.words].reverse() : copy.hero.words;
            return (
              <div key={row} className={`lp-marquee ${row ? 'is-reverse' : ''}`}>
                <div className="lp-marquee-track">
                  {[...words, ...words].map((word, i) => <span key={i} className="lp-pill"><i />{word}</span>)}
                </div>
              </div>
            );
          })}
        </div>
        <p className="sr-only">{copy.hero.words.join(lang === 'zh' ? '、' : ', ')}</p>
      </section>

      <section id="agents" className="lp-section lp-agents">
        <header className="lp-head" data-reveal>
          <p className="lp-eyebrow">{copy.agents.eyebrow}</p>
          <h2><Lines text={copy.agents.title} /></h2>
          <p>{copy.agents.sub}</p>
        </header>
        <div data-reveal>
          <AgentNetwork agents={copy.agents.list} feed={copy.agents.feed} center={copy.agents.center}
            feedTitle={copy.agents.feedTitle} caption={copy.agents.caption} still={!motionOn} />
        </div>
      </section>

      <section id="workflow" className="lp-section lp-workflow">
        <header className="lp-head" data-reveal>
          <p className="lp-eyebrow">{copy.workflow.eyebrow}</p>
          <h2><Lines text={copy.workflow.title} /></h2>
        </header>
        <WorkflowStory copy={copy.workflow} agents={copy.agents.list} />
      </section>

      <section id="capabilities" className="lp-section lp-capabilities">
        <header className="lp-head" data-reveal>
          <p className="lp-eyebrow">{copy.capabilities.eyebrow}</p>
          <h2><Lines text={copy.capabilities.title} /></h2>
        </header>
        <Capabilities items={copy.capabilities.list} lang={lang} />
      </section>

      <section className="lp-statement-wrap" aria-label={copy.statement.text.replace('\n', lang === 'zh' ? '' : ' ')}>
        <div ref={statement} className="lp-statement" style={{ '--n': statementCount } as React.CSSProperties}>
          <div className="lp-statement-sticky">
            <p className="lp-statement-text" aria-hidden="true">
              {(() => {
                let n = 0;
                return statementWords.map((word, i) => (word === '\n'
                  ? <br key={i} />
                  : <span key={i} style={{ '--i': n++ } as React.CSSProperties}>{word}{lang === 'en' ? ' ' : ''}</span>));
              })()}
            </p>
            <p className="lp-statement-sub">{copy.statement.sub}</p>
          </div>
        </div>
      </section>

      <section className="lp-cta" aria-labelledby="lp-cta-title">
        <div className="lp-aurora" aria-hidden="true"><i /><i /><i /></div>
        <div className="lp-cta-inner" data-reveal>
          <h2 id="lp-cta-title"><Lines text={copy.cta.title} /></h2>
          <p>{copy.cta.sub}</p>
          <div className="lp-actions is-center">
            <Link to="/legal" className="lp-btn lp-btn-primary"><span>{copy.cta.primary}</span><ArrowRight size={17} aria-hidden="true" /></Link>
            <Link to="/agent" className="lp-btn lp-btn-ghost">{copy.cta.secondary}<ArrowUpRight size={15} aria-hidden="true" /></Link>
          </div>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-brand">
            <Link to="/" aria-label="CausalGraph"><BrandLogo size="md" tone="dark" /></Link>
            <p>{copy.footer.tagline}</p>
            <LanguageSwitch tone="dark" />
          </div>
          <nav aria-label={copy.footer.product}>
            <h3>{copy.footer.product}</h3>
            <Link to="/legal">{copy.footer.links.legal}</Link>
            <Link to="/agent">{copy.footer.links.research}</Link>
            <Link to="/causal-inference">{copy.footer.links.graph}</Link>
            <Link to="/desktop">{copy.footer.links.desktop}</Link>
          </nav>
          <nav aria-label={copy.footer.company}>
            <h3>{copy.footer.company}</h3>
            <Link to="/about">{copy.footer.links.about}</Link>
            <a href={githubRepositoryUrl} target="_blank" rel="noreferrer">GitHub</a>
          </nav>
        </div>
        <div className="lp-footer-base">
          <span>{copy.footer.disclaimer}</span>
          <span>© {YEAR} CausalGraph · {copy.footer.built}</span>
        </div>
      </footer>
    </div>
  );
}
