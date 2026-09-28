import { useI18n } from '../i18n/useI18n';
import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, LogOut, Menu, ShieldCheck, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import BrandLogo from './BrandLogo';
import LanguageSwitcher from './LanguageSwitcher';

const NAV_LINKS = [
  { name: '法务 Agent', href: '/legal' },
  { name: 'Research', href: '/agent' },
  { name: 'Graph', href: '/causal-inference' },
  { name: 'Desktop', href: '/desktop' },
  { name: 'Company', href: '/about' },
];

const initialOf = (value?: string | null) =>
  String(value || '?').trim().charAt(0).toUpperCase() || '?';

const Navbar: React.FC = () => {
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const { isAuthenticated, logout, user } = useAuth();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';
  const userLabel = user?.username || user?.email || 'Account';

  // Close both menus after navigating.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset on route change; one extra render per navigation
    setIsOpen(false);
    setIsAccountOpen(false);
  }, [location.pathname]);

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

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm transition-colors ${
      isActive ? 'font-medium text-ink' : 'text-ink-3 hover:text-ink'
    }`;

  return (
    <header className={`sticky top-0 z-40 border-b border-line bg-paper ${['/', '/home', '/zh', '/en'].includes(location.pathname) ? 'cg-nav-home' : ''}`}>
      <div className="mx-auto flex h-[60px] max-w-content items-center gap-2 px-3 sm:gap-4 sm:px-8">
        <Link to="/" className="shrink-0 rounded-md" aria-label={t("CausalGraph home")}>
          <BrandLogo size="md" />
        </Link>

        <nav className="hidden items-center gap-0.5 lg:flex" aria-label={t("Primary")}>
          {NAV_LINKS.map((item) => (
            <NavLink key={item.href} to={item.href} className={linkClass}>
              {t(item.name)}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto shrink-0"><LanguageSwitcher /></div>
        <div className="hidden items-center gap-2 lg:flex">
          {isAuthenticated ? (
            <>
              <Link to="/legal" className="btn btn-primary btn-sm">{t("开始审查")}{' '}</Link>
              <div className="relative" ref={accountRef}>
                <button
                  type="button"
                  onClick={() => setIsAccountOpen((prev) => !prev)}
                  className="flex h-8 items-center gap-1.5 rounded-md pl-1 pr-1.5 text-ink-3 transition-colors hover:bg-paper-hover hover:text-ink"
                  aria-expanded={isAccountOpen}
                  aria-haspopup="menu"
                  aria-label={t("Account menu")}
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink text-[11px] font-medium text-white">
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
                        <ShieldCheck className="h-4 w-4 text-ink-4" />{t("Admin console")}{' '}</Link>
                    )}
                    {isAdmin && <Link to="/admin/memberships" className="menu-item" role="menuitem">{t("Max 会员")}</Link>}
                    {isAdmin && <Link to="/admin/recruitment" className="menu-item" role="menuitem">{t("Recruitment")}</Link>}
                    <button type="button" onClick={handleLogout} className="menu-item" role="menuitem">
                      <LogOut className="h-4 w-4 text-ink-4" />{t("Sign out")}{' '}</button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              {location.pathname !== '/login' && (
                <Link to="/login" className="btn btn-ghost btn-sm">{t("Sign in")}{' '}</Link>
              )}
              <Link to="/legal" className="btn btn-primary btn-sm">{t("开始审查")}{' '}</Link>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className="icon-btn shrink-0 lg:hidden"
          aria-label={isOpen ? t("Close menu") : t("Open menu")}
          aria-expanded={isOpen}
        >
          {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {isOpen && (
        <div className="cg-mobile-menu border-t border-line bg-paper px-5 pb-6 pt-2 lg:hidden">
          <nav className="flex flex-col" aria-label={t("Mobile")}>
            {NAV_LINKS.map((item) => (
              <NavLink
                key={item.href}
                to={item.href}
                className={({ isActive }) =>
                  `border-b border-line-soft py-3.5 text-[17px] ${isActive ? 'font-medium text-ink' : 'text-ink-2'}`
                }
              >
                {t(item.name)}
              </NavLink>
            ))}
          </nav>
          <div className="mt-5">
            {isAuthenticated ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-xs font-medium text-white">
                    {initialOf(userLabel)}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{userLabel}</div>
                    {user?.email && <div className="truncate text-xs text-ink-4">{user.email}</div>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link to="/legal" className="btn btn-primary">{t("开始审查")}</Link>
                  {isAdmin && <Link to="/admin" className="btn btn-secondary">{t("Admin console")}</Link>}
                  {isAdmin && <Link to="/admin/memberships" className="btn btn-secondary">{t("Max 会员")}</Link>}
                  {isAdmin && <Link to="/admin/recruitment" className="btn btn-secondary">{t("Recruitment")}</Link>}
                  <button type="button" onClick={handleLogout} className="btn btn-secondary">{t("Sign out")}</button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Link to="/legal" className="btn btn-primary flex-1">{t("开始审查")}</Link>
                <Link to="/login" className="btn btn-secondary flex-1">{t("Sign in")}</Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
