import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronDown, LogOut, Menu, ShieldCheck, UserCircle, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import BrandLogo from './BrandLogo';

// MiniMax-style navigation:
//   white canvas + hairline bottom border, ~64px tall.
//   Left: wordmark.   Center: horizontal text-link list (no chrome).
//   Right: outline-pill secondary + black-pill primary CTA.
const Navbar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const location = useLocation();
  const { isAuthenticated, logout, user } = useAuth();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';

  const navigation = [
    { name: 'Home', href: '/' },
    { name: 'Graph', href: '/causal-inference' },
    { name: 'Desktop', href: '/desktop' },
    { name: 'Company', href: '/about' },
  ];

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname === path;
  const userLabel = user?.username || user?.email || 'Account';

  const handleLogout = () => {
    setIsUserMenuOpen(false);
    setIsOpen(false);
    logout();
  };

  return (
    <nav
      className="sticky top-0 z-50 border-b bg-canvas"
      style={{ borderColor: 'var(--cg-hairline-soft)' }}
    >
      <div
        className="mx-auto grid h-16 max-w-page grid-cols-[auto_1fr_auto] items-center gap-8 px-4 sm:px-6 lg:h-[72px] lg:max-w-page-wide lg:px-8 xl:h-20 xl:max-w-page-xl xl:px-12 2xl:max-w-page-2xl 2xl:px-16"
      >
        {/* Wordmark — scales with viewport so it doesn't look tiny on 2K+ displays. */}
        <Link to="/" className="flex items-center gap-3 lg:gap-3.5 xl:gap-4" aria-label="CausalGraph home">
          <BrandLogo size="nav" />
        </Link>

        {/* Center nav — plain text links (MiniMax-style) */}
        <div className="hidden min-w-0 items-center justify-center md:flex">
          <div className="flex items-center gap-1 xl:gap-2">
            {navigation.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`relative px-4 py-2 text-body-sm font-medium transition xl:px-5 xl:text-body-md ${
                    active
                      ? 'text-ink'
                      : 'text-ink-steel hover:text-ink'
                  }`}
                >
                  {item.name}
                  {active && (
                    <motion.span
                      layoutId="nav-underline"
                      className="absolute inset-x-3 -bottom-[19px] h-[2px] bg-ink xl:-bottom-[23px]"
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Right CTAs */}
        <div className="hidden items-center gap-2 justify-self-end md:flex">
          {isAuthenticated ? (
            <>
              <Link to="/agent" className="cg-btn-primary">
                Open Research Desk
              </Link>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIsUserMenuOpen((prev) => !prev)}
                  className="cg-btn-tertiary max-w-[220px] px-3"
                  aria-expanded={isUserMenuOpen}
                  aria-haspopup="menu"
                >
                  <UserCircle className="h-4 w-4 shrink-0" />
                  <span className="truncate">{userLabel}</span>
                  <ChevronDown className={`h-4 w-4 shrink-0 transition ${isUserMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                {isUserMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.14 }}
                    className="absolute right-0 top-full z-50 mt-2 w-64 rounded-xl border border-hairline bg-white p-2 shadow-card"
                    role="menu"
                  >
                    <div className="border-b border-hairline px-3 py-2">
                      <div className="truncate text-sm font-semibold text-ink">{userLabel}</div>
                      <div className="mt-0.5 truncate text-xs text-ink-steel">{user?.email}</div>
                    </div>
                    {isAdmin && (
                      <Link
                        to="/admin"
                        onClick={() => setIsUserMenuOpen(false)}
                        className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink-charcoal transition hover:bg-surface-soft hover:text-ink"
                        role="menuitem"
                      >
                        <ShieldCheck className="h-4 w-4 text-ink-steel" />
                        Admin console
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-ink-charcoal transition hover:bg-surface-soft hover:text-ink"
                      role="menuitem"
                    >
                      <LogOut className="h-4 w-4 text-ink-steel" />
                      Sign out
                    </button>
                  </motion.div>
                )}
              </div>
            </>
          ) : (
            <>
              <Link to="/login" className="cg-btn-primary">
                Sign in
              </Link>
            </>
          )}
        </div>

        {/* Mobile menu trigger */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="cg-btn-icon justify-self-end md:hidden"
          aria-label={isOpen ? 'Close menu' : 'Open menu'}
        >
          {isOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      {/* Mobile drawer */}
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          className="border-t bg-canvas px-4 pb-4 pt-3 md:hidden"
          style={{ borderColor: 'var(--cg-hairline-soft)' }}
        >
          <div className="space-y-1">
            {navigation.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  onClick={() => setIsOpen(false)}
                  className={`block rounded-lg px-3 py-3 text-body-sm font-medium ${
                    active
                      ? 'bg-surface text-ink'
                      : 'text-ink-steel hover:bg-surface hover:text-ink'
                  }`}
                >
                  {item.name}
                </Link>
              );
            })}
          </div>
          <div className="mt-4 border-t pt-4" style={{ borderColor: 'var(--cg-hairline-soft)' }}>
            {isAuthenticated ? (
              <div className="space-y-3">
                <Link to="/agent" onClick={() => setIsOpen(false)} className="cg-btn-primary w-full">
                  Open Research Desk
                </Link>
                <div className="rounded-xl border border-hairline bg-surface-soft p-2">
                  <div className="px-2 py-2">
                    <div className="truncate text-sm font-semibold text-ink">{userLabel}</div>
                    <div className="mt-0.5 truncate text-xs text-ink-steel">{user?.email}</div>
                  </div>
                  {isAdmin && (
                    <Link
                      to="/admin"
                      onClick={() => setIsOpen(false)}
                      className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm font-medium text-ink-charcoal hover:bg-white hover:text-ink"
                    >
                      <ShieldCheck className="h-4 w-4 text-ink-steel" />
                      Admin console
                    </Link>
                  )}
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-medium text-ink-charcoal hover:bg-white hover:text-ink"
                  >
                    <LogOut className="h-4 w-4 text-ink-steel" />
                    Sign out
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <Link to="/login" onClick={() => setIsOpen(false)} className="cg-btn-primary w-full">
                  Sign in
                </Link>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </nav>
  );
};

export default Navbar;
