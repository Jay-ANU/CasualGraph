import { useEffect, useRef, useState } from 'react';

type Source = { webm: string; mp4: string; poster: string };
const LANDSCAPE: Source = { webm: '/media/hero-legal-1080.webm', mp4: '/media/hero-legal-1080.mp4', poster: '/media/hero-legal-poster.webp' };
const PORTRAIT: Source = { webm: '/media/hero-legal-portrait.webm', mp4: '/media/hero-legal-portrait.mp4', poster: '/media/hero-legal-poster-portrait.webp' };
const PORTRAIT_QUERY = '(max-aspect-ratio: 4/5)';

const isPortrait = () => typeof window.matchMedia === 'function' && window.matchMedia(PORTRAIT_QUERY).matches;

/**
 * The full-bleed hero loop. The poster paints first; the video only plays while the hero is
 * on screen, the tab is visible and motion is allowed, and it never blocks the page.
 */
export default function HeroVideo({ playing, onFirstFrame }: { playing: boolean; onFirstFrame?: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [source, setSource] = useState<Source>(() => (isPortrait() ? PORTRAIT : LANDSCAPE));
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(PORTRAIT_QUERY);
    const update = () => setSource(query.matches ? PORTRAIT : LANDSCAPE);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    const element = video.current;
    if (!element || failed) return;
    // iOS needs the attribute, not only the property, before it allows inline autoplay.
    element.muted = true;
    element.setAttribute('muted', '');
    if (playing) {
      if (element.dataset.src !== source.mp4) {
        element.dataset.src = source.mp4;
        element.load();
      }
      void element.play().catch(() => { /* autoplay refused: the poster stays */ });
    } else {
      element.pause();
    }
  }, [playing, source, failed]);

  return (
    <div className={`lp-hero-media ${ready ? 'is-ready' : ''}`} aria-hidden="true">
      {/* React 18 does not know fetchPriority yet; the lowercase attribute passes through untouched. */}
      <img className="lp-hero-poster" src={source.poster} alt="" decoding="async" {...{ fetchpriority: 'high' }} />
      {!failed && (
        <video
          ref={video}
          className="lp-hero-video"
          muted
          loop
          playsInline
          preload="none"
          disablePictureInPicture
          tabIndex={-1}
          poster={source.poster}
          onPlaying={() => { setReady(true); onFirstFrame?.(); }}
        >
          <source src={source.webm} type="video/webm" />
          {/* The last source failing means no format worked; keep the poster. */}
          <source src={source.mp4} type="video/mp4" onError={() => setFailed(true)} />
        </video>
      )}
    </div>
  );
}
