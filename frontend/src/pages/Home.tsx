import { useEffect, useRef, useState } from 'react';
import { ChevronRight, EyeOff, Lock, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import LanguageSwitch from '../components/LanguageSwitch';
import { githubRepositoryUrl } from '../config/downloads';
import { useI18n } from '../i18n/core';
import useDocumentTitle from '../utils/useDocumentTitle';
import AgentsGallery from './home/AgentsGallery';
import { COPY } from './home/copy';
import HeroVideo from './home/HeroVideo';
import { useReducedMotion, useReveal, useScrollProgress } from './home/motion';
import Redaction from './home/Redaction';
import Tiers from './home/Tiers';
import Tiles from './home/Tiles';
import WorkflowStory from './home/WorkflowStory';
import '@fontsource-variable/inter/wght.css';
import './home/home.css';

const YEAR = new Date().getFullYear();
const saveData = () => Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
const PRIVACY_ICONS = [Lock, EyeOff, ShieldCheck];

/** Headlines carry their own line breaks ("\n") so Chinese never splits mid-phrase. */
function Lines({ text }: { text: string }) {
  return <>{text.split('\n').map((part, i) => <span key={i}>{i > 0 && <br />}{part}</span>)}</>;
}

export default function Home() {
  const { lang } = useI18n();
  const copy = COPY[lang];
  const reduced = useReducedMotion();
  const [lowData] = useState(saveData);
  const motion = !reduced && !lowData;
  const [heroOnScreen, setHeroOnScreen] = useState(true);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const root = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const film = useRef<HTMLDivElement>(null);
  const statement = useRef<HTMLDivElement>(null);
  useDocumentTitle(copy.title);
  useReveal(root, lang);

  // Dark browser chrome on phones while the landing page is open.
  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    const previous = meta?.getAttribute('content');
    meta?.setAttribute('content', '#000000');
    return () => { if (previous) meta?.setAttribute('content', previous); };
  }, []);

  useEffect(() => {
    const element = hero.current;
    if (!element || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(([entry]) => setHeroOnScreen(entry.isIntersecting), { threshold: 0.05 });
    observer.observe(element);
    const onVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibility);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', onVisibility); };
  }, []);

  // The film settles back very slightly as the page scrolls on.
  useEffect(() => {
    const element = film.current;
    if (!element) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = element.getBoundingClientRect();
      const p = Math.min(1, Math.max(0, -rect.top / Math.max(1, rect.height)));
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

  // In-page links glide to their section (and jump straight there when motion is reduced).
  const toSection = (event: React.MouseEvent<HTMLAnchorElement>) => {
    const target = document.getElementById(event.currentTarget.hash.slice(1));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    history.replaceState(history.state, '', event.currentTarget.hash);
  };

  const statementWords = lang === 'zh'
    ? Array.from(copy.statement.text)
    : copy.statement.text.split(/ |(?=\n)|(?<=\n)/).filter(Boolean);
  const statementCount = statementWords.filter(word => word !== '\n').length;

  return (
    <div ref={root} className="ap" lang={lang === 'zh' ? 'zh-CN' : 'en'}>
      <section ref={hero} className="ap-hero" aria-labelledby="ap-hero-title">
        <div className="ap-hero-copy">
          <p className="ap-product"><BrandLogo size="md" showText={false} tone="dark" />{copy.hero.eyebrow}</p>
          <h1 id="ap-hero-title" className="ap-h1" key={lang}><Lines text={copy.hero.title} /></h1>
          <p className="ap-intro">{copy.hero.sub}</p>
          <div className="ap-actions">
            <Link to="/legal" className="ap-btn">{copy.hero.primary}</Link>
            <a href="#workflow" className="ap-link" onClick={toSection}>{copy.hero.secondary}<ChevronRight size={16} strokeWidth={2.4} aria-hidden="true" /></a>
          </div>
        </div>
        <div ref={film} className="ap-hero-film">
          <HeroVideo lang={lang} active={heroOnScreen && pageVisible} motion={motion}
            labels={{ film: copy.hero.film, replay: copy.hero.replay, pause: copy.hero.pause, play: copy.hero.play }} />
        </div>
        <p className="ap-caption ap-hero-note">{copy.hero.note}</p>
      </section>

      <section id="redaction" className="ap-section is-light" aria-labelledby="ap-redaction-title">
        <div className="ap-wrap">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.redaction.eyebrow}</p>
            <h2 id="ap-redaction-title" className="ap-h2"><Lines text={copy.redaction.title} /></h2>
            <p className="ap-intro">{copy.redaction.sub}</p>
          </header>
          <div data-reveal><Redaction copy={copy.redaction} still={!motion} /></div>
        </div>
      </section>

      <section id="workflow" className="ap-section is-dark ap-workflow" aria-labelledby="ap-workflow-title">
        <div className="ap-wrap">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.workflow.eyebrow}</p>
            <h2 id="ap-workflow-title" className="ap-h2"><Lines text={copy.workflow.title} /></h2>
          </header>
        </div>
        <WorkflowStory copy={copy.workflow} />
      </section>

      <section id="agents" className="ap-section is-gray" aria-labelledby="ap-agents-title">
        <div className="ap-wide">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.agents.eyebrow}</p>
            <h2 id="ap-agents-title" className="ap-h2"><Lines text={copy.agents.title} /></h2>
            <p className="ap-intro">{copy.agents.sub}</p>
          </header>
          <div data-reveal><AgentsGallery agents={copy.agents.list} caption={copy.agents.caption} prev={copy.agents.prev} next={copy.agents.next} /></div>
        </div>
      </section>

      <section className="ap-section is-dark" aria-labelledby="ap-stats-title">
        <div className="ap-wrap">
          <h2 id="ap-stats-title" className="ap-h2 ap-center" data-reveal>{copy.stats.title}</h2>
          <dl className="ap-stats" data-reveal>
            {copy.stats.items.map(([value, label]) => (
              <div key={label}><dd>{value}</dd><dt>{label}</dt></div>
            ))}
          </dl>
        </div>
      </section>

      <section id="tiers" className="ap-section is-light" aria-labelledby="ap-tiers-title">
        <div className="ap-wrap">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.tiers.eyebrow}</p>
            <h2 id="ap-tiers-title" className="ap-h2"><Lines text={copy.tiers.title} /></h2>
            <p className="ap-intro">{copy.tiers.sub}</p>
          </header>
          <div data-reveal><Tiers copy={copy.tiers} /></div>
        </div>
      </section>

      <section id="capabilities" className="ap-section is-gray" aria-labelledby="ap-capabilities-title">
        <div className="ap-wide">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.capabilities.eyebrow}</p>
            <h2 id="ap-capabilities-title" className="ap-h2"><Lines text={copy.capabilities.title} /></h2>
          </header>
          <Tiles copy={copy.capabilities} />
        </div>
      </section>

      <section id="privacy" className="ap-section is-dark" aria-labelledby="ap-privacy-title">
        <div className="ap-wrap">
          <header className="ap-head" data-reveal>
            <p className="ap-eyebrow">{copy.privacy.eyebrow}</p>
            <h2 id="ap-privacy-title" className="ap-h2"><Lines text={copy.privacy.title} /></h2>
          </header>
          <ul className="ap-privacy" data-reveal>
            {copy.privacy.items.map((item, i) => {
              const Icon = PRIVACY_ICONS[i] ?? Lock;
              return <li key={item.title}><Icon size={30} strokeWidth={1.5} aria-hidden="true" /><h3>{item.title}</h3><p>{item.body}</p></li>;
            })}
          </ul>
        </div>
      </section>

      <section id="models" className="ap-section is-light" aria-labelledby="ap-models-title">
        <div className="ap-wrap">
          <header className="ap-head" data-reveal>
            <h2 id="ap-models-title" className="ap-h2">{copy.models.title}</h2>
            <p className="ap-intro">{copy.models.sub}</p>
          </header>
          <ul className="ap-wordmarks" data-reveal>{copy.models.list.map(name => <li key={name}>{name}</li>)}</ul>
        </div>
      </section>

      <section className="ap-statement-wrap" aria-label={copy.statement.text.replace('\n', lang === 'zh' ? '' : ' ')}>
        <div ref={statement} className="ap-statement" style={{ '--n': statementCount } as React.CSSProperties}>
          <div className="ap-statement-sticky">
            <p className="ap-statement-text" aria-hidden="true">
              {(() => {
                let n = 0;
                return statementWords.map((word, i) => (word === '\n'
                  ? <br key={i} />
                  : <span key={i} style={{ '--i': n++ } as React.CSSProperties}>{word}{lang === 'en' ? ' ' : ''}</span>));
              })()}
            </p>
            <p className="ap-statement-sub">{copy.statement.sub}</p>
          </div>
        </div>
      </section>

      <section className="ap-section is-gray ap-cta" aria-labelledby="ap-cta-title">
        <div className="ap-wrap" data-reveal>
          <h2 id="ap-cta-title" className="ap-h2"><Lines text={copy.cta.title} /></h2>
          <p className="ap-intro">{copy.cta.sub}</p>
          <div className="ap-actions">
            <Link to="/legal" className="ap-btn">{copy.cta.primary}</Link>
            <Link to="/agent" className="ap-link">{copy.cta.secondary}<ChevronRight size={16} strokeWidth={2.4} aria-hidden="true" /></Link>
          </div>
        </div>
      </section>

      <footer className="ap-footer">
        <div className="ap-wide ap-footer-inner">
          <div className="ap-footer-brand">
            <Link to="/" aria-label="CausalGraph"><BrandLogo size="sm" /></Link>
            <p>{copy.footer.tagline}</p>
            <LanguageSwitch />
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
        <div className="ap-wide ap-footer-base">
          <span>{copy.footer.disclaimer}</span>
          <span>© {YEAR} CausalGraph · {copy.footer.built}</span>
        </div>
      </footer>
    </div>
  );
}
