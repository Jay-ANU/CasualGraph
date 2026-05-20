/* global React */
const { useState } = React;

/* ----- Button ----- */
function Button({ variant = 'primary', icon: Icon, iconRight, children, className = '', size = 'md', onClick, type='button' }) {
  const base = 'inline-flex items-center justify-center gap-2 font-semibold transition disabled:opacity-50 whitespace-nowrap';
  const sizes = {
    md: 'px-[18px] py-[10px] text-sm rounded-xl',
    sm: 'px-3 py-1.5 text-[13px] rounded-lg',
  };
  const variants = {
    primary: 'bg-slate-950 text-white hover:bg-slate-800 shadow-sm',
    secondary: 'border border-slate-200 bg-white/72 text-slate-900 hover:bg-white',
    ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
    danger: 'border border-red-200 bg-red-50 text-red-700 hover:bg-red-100',
  };
  return (
    <button type={type} onClick={onClick} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
      {iconRight ? React.createElement(iconRight, { className: 'h-4 w-4' }) : null}
    </button>
  );
}

/* ----- IconButton ----- */
function IconButton({ icon: Icon, onClick, label, className = '' }) {
  return (
    <button onClick={onClick} aria-label={label} title={label}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition ${className}`}>
      <Icon className="h-4 w-4" />
    </button>
  );
}

/* ----- EyebrowChip ----- */
function EyebrowChip({ icon: Icon, children }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white/72 px-3 py-2 text-sm font-semibold text-slate-700">
      {Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </div>
  );
}

/* ----- Pill (filter / mode) ----- */
function Pill({ icon: Icon, children, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition ${
        active ? 'bg-slate-950 text-white border-slate-950' : 'bg-white/72 text-slate-600 border-slate-200 hover:bg-white'
      }`}>
      {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
      {children}
    </button>
  );
}

/* ----- Input + Field ----- */
function Input({ icon: Icon, ...rest }) {
  if (!Icon) {
    return <input {...rest} className={`w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-200 ${rest.className||''}`} />;
  }
  return (
    <div className="relative">
      <Icon className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
      <input {...rest} className={`w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-200 ${rest.className||''}`} />
    </div>
  );
}
function Field({ label, hint, children }) {
  return (
    <label className="block">
      <div className="mb-1.5 text-[12px] font-medium text-slate-700">{label}</div>
      {children}
      {hint ? <div className="mt-1 text-[11.5px] text-slate-500">{hint}</div> : null}
    </label>
  );
}

/* ----- Tag + DomainTag ----- */
function Tag({ children }) {
  return <span className="inline-flex items-center rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">{children}</span>;
}
const DOMAIN_STYLES = {
  Environmental: 'bg-emerald-50 text-emerald-700',
  Social: 'bg-blue-50 text-blue-700',
  Governance: 'bg-amber-50 text-amber-800',
  General: 'bg-slate-100 text-slate-600',
  AI: 'bg-violet-50 text-violet-700',
};
function DomainTag({ domain }) {
  const cls = DOMAIN_STYLES[domain] || DOMAIN_STYLES.General;
  return <span className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium ${cls}`}>{domain}</span>;
}

/* ----- Panel (the codebase's `.app-panel`) ----- */
function Panel({ children, className = '' }) {
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white/86 shadow-[0_8px_24px_rgba(15,23,42,0.06)] ${className}`}>
      {children}
    </div>
  );
}

Object.assign(window, { Button, IconButton, EyebrowChip, Pill, Input, Field, Tag, DomainTag, Panel });
