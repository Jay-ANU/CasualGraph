import { useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { useI18n } from '../i18n/useI18n';
import './motion.css';

const PREF = 'causalgraph.motion-paused';
const QUERY = '(prefers-reduced-motion: reduce)';
const systemReduced = () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches;
const savedPause = () => { try { return localStorage.getItem(PREF) === 'true'; } catch { return false; } };
const saveData = () => Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);

/** Same-origin, original silent video. No third-party player, analytics or client data. */
export default function LegalMotion({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  const container = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [reduced, setReduced] = useState(systemReduced);
  const [paused, setPaused] = useState(() => savedPause() || saveData());
  const [visible, setVisible] = useState(false);
  const [hidden, setHidden] = useState(() => document.hidden);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [hasFrame, setHasFrame] = useState(false);
  const active = !paused && !reduced && visible && !hidden && !failed;
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const change = () => {
      setReduced(media.matches);
      if (media.matches) { video.current?.pause(); setPlaying(false); setHasFrame(false); }
    };
    const visibility = () => setHidden(document.hidden);
    const sync = (event: Event) => setPaused(Boolean((event as CustomEvent<boolean>).detail));
    const storage = (event: StorageEvent) => { if (event.key === PREF) setPaused(event.newValue === 'true'); };
    media.addEventListener('change', change);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('cg-motion-change', sync);
    window.addEventListener('storage', storage);
    const observer = new IntersectionObserver(entries => setVisible(entries[0]?.isIntersecting ?? false), { threshold: 0.12 });
    if (container.current) observer.observe(container.current);
    return () => { observer.disconnect(); media.removeEventListener('change', change);
      document.removeEventListener('visibilitychange', visibility); window.removeEventListener('cg-motion-change', sync); window.removeEventListener('storage', storage); };
  }, []);
  useEffect(() => {
    const player = video.current;
    if (!player) return;
    if (active) {
      // Attach the asset only when motion is requested; keep it attached when paused.
      if (!player.getAttribute('src')) { player.src = '/media/legal-motion.mp4'; }
      void player.play().catch(() => { /* Autoplay can be blocked. Keep the poster and offer a play button. */ });
    } else player.pause();
  }, [active]);
  const toggle = () => {
    // A real user gesture may start video even after a browser blocked autoplay.
    const next = playing;
    setPaused(Boolean(next));
    try { localStorage.setItem(PREF, String(Boolean(next))); } catch { /* In-memory preference still works. */ }
    window.dispatchEvent(new CustomEvent<boolean>('cg-motion-change', { detail: Boolean(next) }));
    if (!next && !reduced && video.current) {
      if (!video.current.getAttribute('src')) { video.current.src = '/media/legal-motion.mp4'; }
      void video.current.play().catch(() => {});
    }
  };
  return <div ref={container} className={`cg-legal-motion ${compact ? 'is-compact' : ''} ${playing ? 'is-playing' : 'is-still'} ${hasFrame ? 'has-frame' : ''}`}>
    <img className="cg-motion-poster" src="/media/legal-motion-poster.webp" alt="" width={960} height={800} aria-hidden="true" fetchPriority={compact ? 'auto' : 'high'} />
    {!reduced && !failed && <video ref={video} className="cg-motion-video" muted loop playsInline preload="none"
      poster="/media/legal-motion-poster.webp"
      aria-hidden="true" tabIndex={-1} disablePictureInPicture
      onPlaying={() => { setPlaying(true); setHasFrame(true); }} onPause={() => setPlaying(false)}
      onError={() => { setFailed(true); setPlaying(false); setHasFrame(false); }}
      onCanPlay={() => { if (active) void video.current?.play().catch(() => {}); }} />}
    <div className="cg-motion-caption"><span>{t('法务工作流 · 动态示意')}</span>
      {!reduced && !failed && <button type="button" onClick={toggle} aria-label={playing ? t('暂停动态效果') : t('播放动态效果')} aria-pressed={playing}>
        {playing ? <Pause size={12} aria-hidden="true" /> : <Play size={12} aria-hidden="true" />}{playing ? t('暂停') : t('播放')}
      </button>}
      {(reduced || failed) && <span>{t('静态预览')}</span>}
    </div>
  </div>;
}
