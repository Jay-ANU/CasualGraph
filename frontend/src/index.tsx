import React from 'react';
import ReactDOM from 'react-dom/client';
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
