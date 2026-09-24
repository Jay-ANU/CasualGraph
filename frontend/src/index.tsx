import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/400-italic.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource-variable/newsreader/opsz.css';
import './index.css';
import 'katex/dist/katex.min.css';
import App from './App';

const ObjectWithHasOwn = Object as ObjectConstructor & {
  hasOwn?: (object: object, property: PropertyKey) => boolean;
};

if (!ObjectWithHasOwn.hasOwn) {
  ObjectWithHasOwn.hasOwn = (object: object, property: PropertyKey) =>
    Object.prototype.hasOwnProperty.call(object, property);
}

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
