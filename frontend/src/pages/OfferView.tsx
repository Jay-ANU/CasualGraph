import { apiBase as restoredApiBase } from '../api/config';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import useDocumentTitle from '../utils/useDocumentTitle';
import OfferExperience, { OfferLoading, OfferNotice } from './offer/OfferExperience';
import { OfferDecision, PublicOffer, copyFor } from './offer/offerContent';

const apiBase = () => {
  const host = window.location.hostname || '127.0.0.1';
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  return restoredApiBase() || (localApiHost ? `http://${host}:8000` : '');
};

type LoadState = 'loading' | 'ready' | 'invalid' | 'error';

// Keeps the page on warm paper while it is open (no flash on overscroll) and out of search results.
const useOfferPageChrome = () => {
  useEffect(() => {
    const previousBackground = document.body.style.background;
    document.body.style.background = '#FBFAF8';
    const robots = document.createElement('meta');
    robots.name = 'robots';
    robots.content = 'noindex, nofollow';
    document.head.appendChild(robots);
    return () => {
      document.body.style.background = previousBackground;
      robots.remove();
    };
  }, []);
};

/** Public page a candidate reaches from the link in their offer email. */
const OfferView: React.FC = () => {
  const { token = '' } = useParams();
  const base = useMemo(apiBase, []);
  const [state, setState] = useState<LoadState>('loading');
  const [offer, setOffer] = useState<PublicOffer | null>(null);
  useDocumentTitle(offer ? `${offer.position} offer` : 'Your offer');
  useOfferPageChrome();

  const load = useCallback(async () => {
    setState('loading');
    try {
      const response = await fetch(`${base}/offers/${encodeURIComponent(token)}`);
      if (response.status === 404) {
        setState('invalid');
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setOffer((await response.json()) as PublicOffer);
      setState('ready');
    } catch {
      setState('error');
    }
  }, [base, token]);

  useEffect(() => {
    load();
  }, [load]);

  const respond = useCallback(
    async (decision: OfferDecision, note: string) => {
      const response = await fetch(`${base}/offers/${encodeURIComponent(token)}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, note }),
      });
      let payload: any = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }
      if (response.status === 409 && payload?.detail?.offer) {
        // Someone already answered (or the offer was withdrawn); show where things stand.
        setOffer(payload.detail.offer as PublicOffer);
        return;
      }
      if (!response.ok) {
        const detail = payload?.detail;
        throw new Error(typeof detail === 'string' ? detail : copyFor(offer?.language).respondFailed);
      }
      setOffer(payload as PublicOffer);
    },
    [base, token, offer?.language]
  );

  if (state === 'loading') return <OfferLoading />;
  if (state === 'invalid' || (state === 'ready' && !offer)) {
    const copy = copyFor();
    return <OfferNotice title={copy.invalidTitle} body={copy.invalidBody} />;
  }
  if (state === 'error') {
    const copy = copyFor();
    return <OfferNotice title={copy.errorTitle} body={copy.errorBody} actionLabel={copy.retry} onAction={load} />;
  }
  if (offer && offer.status === 'withdrawn') {
    const copy = copyFor(offer.language);
    return <OfferNotice title={copy.withdrawnTitle} body={copy.withdrawnBody(offer.sender_name)} language={offer.language} />;
  }
  return offer ? <OfferExperience offer={offer} onRespond={respond} /> : null;
};

export default OfferView;
