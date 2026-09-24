import { useEffect } from 'react';

const APP_NAME = 'CausalGraph';

/** Sets the browser tab title, e.g. "Library · CausalGraph". */
export default function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
