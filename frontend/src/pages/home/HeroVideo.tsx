import { useEffect, useRef, useState } from 'react';
import { Pause, Play, RotateCcw } from 'lucide-react';

type Props = {
  lang: 'zh' | 'en';
  /** The hero is on screen and the tab is visible. */
  active: boolean;
  /** Motion is allowed: no reduced-motion preference and no Save-Data. */
  motion: boolean;
  labels: { film: string; replay: string; pause: string; play: string };
};
type Orientation = 'landscape' | 'portrait';
const PORTRAIT_QUERY = '(max-aspect-ratio: 4/5)';
const PAUSE_KEY = 'causalgraph.film-paused';

const orientationNow = (): Orientation =>
  typeof window.matchMedia === 'function' && window.matchMedia(PORTRAIT_QUERY).matches ? 'portrait' : 'landscape';
const src = (lang: string, o: Orientation, ext: string) => `/media/film-${lang}-${o}${ext}`;
const savedPause = () => { try { return localStorage.getItem(PAUSE_KEY) === '1'; } catch { return false; } };

/**
 * The product film: a real pass through the contract desk, from upload to a tracked-changes
 * export. It plays once while the hero is on screen, then offers a replay. The poster paints
 * first, the film fades in on its first frame, and nothing here can block the page.
 */
export default function HeroVideo({ lang, active, motion, labels }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [orientation, setOrientation] = useState<Orientation>(orientationNow);
  const [paused, setPaused] = useState(savedPause);
  const [state, setState] = useState<'poster' | 'playing' | 'ended'>('poster');
  const [failed, setFailed] = useState(false);
  const shouldPlay = motion && active && !paused && state !== 'ended' && !failed;

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(PORTRAIT_QUERY);
    const update = () => setOrientation(query.matches ? 'portrait' : 'landscape');
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  // A new language or orientation is a new film: start it from the beginning.
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.load();
    setState('poster');
    setFailed(false);
  }, [lang, orientation]);

  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.muted = true;
    element.setAttribute('muted', '');
    if (shouldPlay) void element.play().catch(() => { /* autoplay refused: the poster stays, the button still works */ });
    else element.pause();
  }, [shouldPlay, lang, orientation]);

  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (state === 'ended') {
      element.currentTime = 0;
      setState('poster');
      setPaused(false);
      try { localStorage.setItem(PAUSE_KEY, '0'); } catch { /* this visit only */ }
      void element.play().catch(() => {});
      return;
    }
    const next = !paused;
    setPaused(next);
    try { localStorage.setItem(PAUSE_KEY, next ? '1' : '0'); } catch { /* this visit only */ }
    if (!next) void element.play().catch(() => {});
  };

  const label = state === 'ended' ? labels.replay : paused || !shouldPlay ? labels.play : labels.pause;
  const Icon = state === 'ended' ? RotateCcw : paused || !shouldPlay ? Play : Pause;
  return (
    <figure className={`ap-film is-${orientation} ${state === 'playing' ? 'is-playing' : ''}`}>
      <img className="ap-film-poster" src={src(lang, orientation, '-poster.webp')} alt="" decoding="async" {...{ fetchpriority: 'high' }} />
      {!failed && (
        <video
          ref={video}
          className="ap-film-video"
          muted
          playsInline
          preload={motion ? 'auto' : 'metadata'}
          disablePictureInPicture
          tabIndex={-1}
          poster={src(lang, orientation, '-poster.webp')}
          aria-label={labels.film}
          onPlaying={() => setState('playing')}
          onEnded={() => setState('ended')}
        >
          <source src={src(lang, orientation, '.webm')} type="video/webm" />
          {/* The last source failing means no format played; the poster stays. */}
          <source src={src(lang, orientation, '.mp4')} type="video/mp4" onError={() => setFailed(true)} />
        </video>
      )}
      {motion && !failed && (
        <button type="button" className="ap-film-control" onClick={toggle} aria-label={label} title={label} data-state={state === 'ended' ? 'ended' : paused ? 'paused' : 'playing'}>
          <Icon size={15} strokeWidth={2.2} aria-hidden="true" />
        </button>
      )}
      <figcaption className="sr-only">{labels.film}</figcaption>
    </figure>
  );
}
