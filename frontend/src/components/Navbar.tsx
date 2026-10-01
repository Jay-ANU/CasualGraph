import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ArrowRight, ChevronDown, LogOut, Menu, ShieldCheck, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../i18n/core';
import BrandLogo from './BrandLogo';
import LanguageSwitch from './LanguageSwitch';

const initialOf = (value?: string | null) =>
  String(value || '?').trim().charAt(0).toUpperCase() || '?';

const Navbar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const [scrolled, setScrolled] = useState(() => window.scrollY > 16);
  const accountRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const { isAuthenticated, logout, user } = useAuth();
  const { tx } = useI18n();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';
  const userLabel = user?.username || user?.email || tx('账户', 'Account');
  // The landing page runs edge to edge under a transparent bar that turns to glass on scroll.
  const overlay = location.pathname === '/' || location.pathname === '/home';
  const dark = overlay;

  const links = [
    { name: tx('法务 Agent', 'Legal Agent'), href: '/legal' },
    { name: tx('研究工作台', 'Research'), href: '/agent' },
    { name: tx('知识图谱', 'Graph'), href: '/causal-inference' },
    { name: tx('桌面应用', 'Desktop'), href: '/desktop' },
    { name: tx('关于我们', 'Company'), href: '/about' },
  ];

  // Close both menus after navigating.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset on route change; one extra render per navigation
    setIsOpen(false);
    setIsAccountOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!overlay) return;
    const onScroll = () => setScrolled(window.scrollY > 16);
    const first = requestAnimationFrame(onScroll);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => { cancelAnimationFrame(first); window.removeEventListener('scroll', onScroll); };
  }, [overlay]);

  useEffect(() => {
    if (!isAccountOpen) return;
    const close = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setIsAccountOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsAccountOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [isAccountOpen]);

  const handleLogout = () => {
    setIsAccountOpen(false);
    setIsOpen(false);
    logout();
  };

  const linkClass = ({ isActive }: { isActive: boolean }) => dark
    ? `rounded-md px-3 py-1.5 text-[13px] transition-colors ${isActive ? 'font-medium text-white' : 'text-white/80 hover:text-white'}`
    : `rounded-md px-3 py-1.5 text-sm transition-colors ${isActive ? 'font-medium text-ink' : 'text-ink-3 hover:text-ink'}`;
  const primaryLabel = isAuthenticated ? tx('进入法务工作台', 'Open legal desk') : tx('开始审查', 'Start a review');
  const shell = overlay
    ? `fixed inset-x-0 top-0 z-40 cg-nav-glass ${scrolled || isOpen ? 'is-scrolled' : ''}`
    : 'sticky top-0 z-40 border-b border-line bg-paper';

  return (
    <header className={shell}>
      <div className={`mx-auto flex max-w-[1320px] items-center gap-6 px-5 sm:px-8 ${overlay ? 'h-[52px]' : 'h-[64px]'}`}>
        <Link to="/" className="shrink-0 rounded-md" aria-label={tx('CausalGraph 首页', 'CausalGraph home')}>
          <BrandLogo size="md" tone={dark ? 'dark' : 'light'} />
        </Link>

        <nav className="hidden items-center gap-0.5 lg:flex" aria-label={tx('主导航', 'Primary')}>
          {links.map((item) => (
            <NavLink key={item.href} to={item.href} className={linkClass}>
              {item.name}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-2.5 lg:flex">
          <LanguageSwitch tone={dark ? 'dark' : 'light'} />
          {isAuthenticated ? (
            <div className="relative" ref={accountRef}>
              <button
                type="button"
                onClick={() => setIsAccountOpen((prev) => !prev)}
                className={`flex h-8 items-center gap-1.5 rounded-md pl-1 pr-1.5 transition-colors ${dark ? 'text-white/75 hover:bg-white/10 hover:text-white' : 'text-ink-3 hover:bg-paper-hover hover:text-ink'}`}
                aria-expanded={isAccountOpen}
                aria-haspopup="menu"
                aria-label={tx('账户菜单', 'Account menu')}
              >
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-medium ${dark ? 'bg-white text-[#0b0a16]' : 'bg-ink text-white'}`}>
                  {initialOf(userLabel)}
                </span>
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isAccountOpen ? 'rotate-180' : ''}`} />
              </button>

              {isAccountOpen && (
                <div className="menu absolute right-0 top-full z-50 mt-2 w-64" role="menu">
                  <div className="px-2.5 pb-2 pt-1.5">
                    <div className="truncate text-sm font-medium text-ink">{userLabel}</div>
                    {user?.email && <div className="truncate text-xs text-ink-4">{user.email}</div>}
                  </div>
                  <div className="menu-sep" />
                  {isAdmin && (
                    <Link to="/admin" className="menu-item" role="menuitem">
                      <ShieldCheck className="h-4 w-4 text-ink-4" />
                      {tx('管理后台', 'Admin console')}
                    </Link>
                  )}
                  {isAdmin && <Link to="/admin/memberships" className="menu-item" role="menuitem">{tx('Max 会员', 'Max memberships')}</Link>}
                  {isAdmin && <Link to="/admin/recruitment" className="menu-item" role="menuitem">{tx('招聘管理', 'Recruitment')}</Link>}
                  <button type="button" onClick={handleLogout} className="menu-item" role="menuitem">
                    <LogOut className="h-4 w-4 text-ink-4" />
                    {tx('退出登录', 'Sign out')}
                  </button>
                </div>
              )}
            </div>
          ) : (
            location.pathname !== '/login' && (
              <Link to="/login" className={dark ? 'btn btn-sm text-white/80 hover:bg-white/10 hover:text-white' : 'btn btn-ghost btn-sm'}>
                {tx('登录', 'Sign in')}
              </Link>
            )
          )}
          <Link to="/legal" className={dark ? 'cg-nav-cta' : 'btn btn-primary btn-sm'}>
            {primaryLabel}
            {dark && <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />}
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className={`icon-btn ml-auto lg:hidden ${dark ? 'text-white hover:bg-white/10 hover:text-white' : ''}`}
          aria-label={isOpen ? tx('关闭菜单', 'Close menu') : tx('打开菜单', 'Open menu')}
          aria-expanded={isOpen}
        >
          {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {isOpen && (
        <div className={`border-t px-5 pb-6 pt-2 lg:hidden ${dark ? 'border-white/10 text-white' : 'border-line bg-paper'}`}>
          <nav className="flex flex-col" aria-label={tx('移动端导航', 'Mobile')}>
            {links.map((item) => (
              <NavLink
                key={item.href}
                to={item.href}
                className={({ isActive }) => dark
                  ? `border-b border-white/10 py-3.5 text-[17px] ${isActive ? 'font-medium text-white' : 'text-white/80'}`
                  : `border-b border-line-soft py-3.5 text-[17px] ${isActive ? 'font-medium text-ink' : 'text-ink-2'}`}
              >
                {item.name}
              </NavLink>
            ))}
          </nav>
          <div className="mt-5 space-y-4">
            <LanguageSwitch tone={dark ? 'dark' : 'light'} />
            {isAuthenticated ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium ${dark ? 'bg-white text-[#0b0a16]' : 'bg-ink text-white'}`}>
                    {initialOf(userLabel)}
                  </span>
                  <div className="min-w-0">
                    <div className={`truncate text-sm font-medium ${dark ? 'text-white' : 'text-ink'}`}>{userLabel}</div>
                    {user?.email && <div className={`truncate text-xs ${dark ? 'text-white/60' : 'text-ink-4'}`}>{user.email}</div>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link to="/legal" className="btn btn-primary">{primaryLabel}</Link>
                  {isAdmin && <Link to="/admin" className="btn btn-secondary">{tx('管理后台', 'Admin console')}</Link>}
                  {isAdmin && <Link to="/admin/memberships" className="btn btn-secondary">{tx('Max 会员', 'Max memberships')}</Link>}
                  {isAdmin && <Link to="/admin/recruitment" className="btn btn-secondary">{tx('招聘管理', 'Recruitment')}</Link>}
                  <button type="button" onClick={handleLogout} className="btn btn-secondary">{tx('退出登录', 'Sign out')}</button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Link to="/legal" className={dark ? 'cg-nav-cta flex-1 justify-center' : 'btn btn-primary flex-1'}>{primaryLabel}</Link>
                <Link to="/login" className={dark ? 'btn flex-1 border border-white/20 text-white hover:bg-white/10' : 'btn btn-secondary flex-1'}>{tx('登录', 'Sign in')}</Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
