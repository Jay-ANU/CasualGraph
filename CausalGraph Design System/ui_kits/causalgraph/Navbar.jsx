/* global React */
const { useState } = React;

function Navbar({ page, onNavigate, authed, onSignOut }) {
  const items = [
    { id: 'home', name: 'Home', icon: 'home' },
    { id: 'desk', name: 'Research Desk', icon: 'database' },
    { id: 'graph', name: 'Graph Engine', icon: 'network' },
    { id: 'about', name: 'Company', icon: 'building-2' },
  ];
  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200 bg-white/78 backdrop-blur-2xl">
      <div className="grid h-[72px] w-full grid-cols-[auto_1fr_auto] items-center gap-4 px-4 sm:px-6 lg:px-8">
        <a onClick={() => onNavigate('home')} className="flex items-center gap-3 cursor-pointer">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm">
            <i data-lucide="orbit" className="h-5 w-5"></i>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">ESG Intelligence</div>
            <span className="text-lg font-semibold text-slate-950">CausalGraph</span>
          </div>
        </a>

        <div className="hidden md:flex min-w-0 items-center justify-center">
          <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white/62 p-1 shadow-sm">
            {items.map(item => {
              const active = item.id === page;
              return (
                <a key={item.id} onClick={() => onNavigate(item.id)}
                  className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition cursor-pointer ${
                    active ? 'bg-slate-950 text-white shadow-sm' : 'text-slate-600 hover:bg-white/80 hover:text-slate-950'
                  }`}>
                  <i data-lucide={item.icon} className="h-4 w-4"></i>
                  {item.name}
                </a>
              );
            })}
          </div>
        </div>

        <div className="hidden md:flex items-center gap-2 justify-self-end">
          {authed ? (
            <>
              <button onClick={() => onNavigate('desk')} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800">Open desk</button>
              <button onClick={onSignOut} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition">Sign out</button>
            </>
          ) : (
            <button onClick={() => onNavigate('login')} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800">Sign in</button>
          )}
        </div>
      </div>
    </nav>
  );
}

window.Navbar = Navbar;
