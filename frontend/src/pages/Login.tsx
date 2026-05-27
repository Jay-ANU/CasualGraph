import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import BrandLogo from '../components/BrandLogo';

type Mode = 'login' | 'register';
type RegisterRole = 'user' | 'admin';

// MiniMax-style auth surface:
//   white canvas, no glassy gradients. A single quiet card (16px radius)
//   centered on the page. Inputs use the spec's text-input chrome with
//   brand-blue-deep focus border. Primary CTA is a black pill.
const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [emailCode, setEmailCode] = useState('');
  const [emailCodeSending, setEmailCodeSending] = useState(false);
  const [emailCodeSent, setEmailCodeSent] = useState(false);
  const [emailCodeCooldown, setEmailCodeCooldown] = useState(0);
  const [registerRole, setRegisterRole] = useState<RegisterRole>('user');
  const [adminInviteCode, setAdminInviteCode] = useState('');

  const host = window.location.hostname || '127.0.0.1';
  const localApiHost = host === 'localhost' || host === '127.0.0.1';
  const apiBase = process.env.REACT_APP_ESG_API_BASE || (localApiHost ? `http://${host}:8000` : '');

  const fetchCaptcha = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/auth/captcha`);
      const data = await res.json();
      setCaptchaId(data.captcha_id);
      setCaptchaImage(data.image);
      setCaptchaCode('');
    } catch {
      setError('Failed to load captcha');
    }
  }, [apiBase]);

  useEffect(() => {
    if (mode === 'register') fetchCaptcha();
  }, [mode, fetchCaptcha]);

  useEffect(() => {
    if (emailCodeCooldown <= 0) return;
    const timer = window.setTimeout(() => setEmailCodeCooldown((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [emailCodeCooldown]);

  const handleSendEmailCode = async () => {
    setError('');
    if (!email.trim()) {
      setError('Enter your email first');
      return;
    }
    if (!captchaId || !captchaCode.trim()) {
      setError('Enter the image captcha before sending the email code');
      return;
    }
    setEmailCodeSending(true);
    try {
      const res = await fetch(`${apiBase}/auth/email-code/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          captcha_id: captchaId,
          captcha_code: captchaCode,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Unable to send email code');
      setEmailCodeSent(true);
      setEmailCode('');
      setEmailCodeCooldown(Number(data.cooldown_seconds || 60));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to send email code');
    } finally {
      setEmailCodeSending(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const endpoint = mode === 'login' ? '/auth/login' : '/auth/register';
      const body = mode === 'login'
        ? { email, password }
        : {
            email,
            username,
            password,
            captcha_id: captchaId,
            captcha_code: captchaCode,
            email_code: emailCode,
            role: registerRole,
            admin_invite_code: registerRole === 'admin' ? adminInviteCode : undefined,
          };

      const res = await fetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');
      login(data.token, data.user);
      const from = (location.state as { from?: { pathname?: string; search?: string; hash?: string } } | null)?.from;
      const redirectTo =
        from?.pathname && from.pathname !== '/login'
          ? `${from.pathname}${from.search || ''}${from.hash || ''}`
          : '/agent';
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
      if (mode === 'register') fetchCaptcha();
    } finally {
      setLoading(false);
    }
  };

  // Local input style — reused so focus state is consistent across fields.
  const inputClass =
    'w-full rounded-md border bg-canvas px-4 py-2.5 text-body-md text-ink outline-none ' +
    'transition focus:border-2 focus:border-brand-blue-deep';

  return (
    <div className="min-h-screen bg-canvas">
      <div className="mx-auto flex min-h-screen max-w-page items-center justify-center px-4 py-section sm:px-6 lg:px-8">
        <div className="w-full max-w-[460px]">
          {/* Brand mark */}
          <div className="mb-10 flex items-center gap-3">
            <BrandLogo size="md" />
          </div>

          <h1
            className="font-display text-heading-md font-semibold text-ink"
            style={{ letterSpacing: 0, lineHeight: 1.20 }}
          >
            {mode === 'login' ? 'Sign in' : 'Create your account'}
          </h1>
          <p className="mt-3 text-body-md text-ink-steel">
            {mode === 'login'
              ? 'Welcome back. Continue your research workspace.'
              : 'Set up your workspace to start querying reports.'}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div>
              <label className="mb-2 block text-caption font-semibold text-ink">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
                style={{ borderColor: 'var(--cg-hairline)' }}
                placeholder="you@example.com"
              />
            </div>

            {mode === 'register' && (
              <div>
                <label className="mb-2 block text-caption font-semibold text-ink">Account type</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setRegisterRole('user')}
                    className={
                      registerRole === 'user'
                        ? 'cg-pill-tab cg-pill-tab--active'
                        : 'cg-pill-tab'
                    }
                  >
                    User
                  </button>
                  <button
                    type="button"
                    onClick={() => setRegisterRole('admin')}
                    className={
                      registerRole === 'admin'
                        ? 'cg-pill-tab cg-pill-tab--active'
                        : 'cg-pill-tab'
                    }
                  >
                    Admin
                  </button>
                </div>
              </div>
            )}

            {mode === 'register' && (
              <div>
                <label className="mb-2 block text-caption font-semibold text-ink">Username</label>
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={inputClass}
                  style={{ borderColor: 'var(--cg-hairline)' }}
                  placeholder="Your name"
                />
              </div>
            )}

            {mode === 'register' && registerRole === 'admin' && (
              <div>
                <label className="mb-2 block text-caption font-semibold text-ink">Admin invite code</label>
                <input
                  type="text"
                  required
                  value={adminInviteCode}
                  onChange={(e) => setAdminInviteCode(e.target.value.toUpperCase())}
                  className={inputClass}
                  style={{ borderColor: 'var(--cg-hairline)' }}
                  placeholder="ADM-XXXXXXXXXX"
                />
              </div>
            )}

            <div>
              <label className="mb-2 block text-caption font-semibold text-ink">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                style={{ borderColor: 'var(--cg-hairline)' }}
                placeholder="••••••••"
              />
            </div>

            {mode === 'register' && (
              <div>
                <label className="mb-2 block text-caption font-semibold text-ink">Image captcha</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    required
                    inputMode="numeric"
                    maxLength={4}
                    value={captchaCode}
                    onChange={(e) => setCaptchaCode(e.target.value.replace(/\D/g, ''))}
                    className={`${inputClass} flex-1`}
                    style={{ borderColor: 'var(--cg-hairline)' }}
                    placeholder="4 digits"
                  />
                  {captchaImage && (
                    <img
                      src={captchaImage}
                      alt="captcha"
                      onClick={fetchCaptcha}
                      className="h-10 cursor-pointer rounded-md border bg-canvas"
                      style={{ borderColor: 'var(--cg-hairline)' }}
                      title="Click to refresh"
                    />
                  )}
                  <button
                    type="button"
                    onClick={fetchCaptcha}
                    className="cg-btn-icon"
                    title="Refresh captcha"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            {mode === 'register' && (
              <div>
                <label className="mb-2 block text-caption font-semibold text-ink">Email verification code</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    required
                    inputMode="numeric"
                    maxLength={6}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, ''))}
                    className={`${inputClass} flex-1`}
                    style={{ borderColor: 'var(--cg-hairline)' }}
                    placeholder="6 digits"
                  />
                  <button
                    type="button"
                    onClick={handleSendEmailCode}
                    disabled={emailCodeSending || emailCodeCooldown > 0}
                    className="rounded-md border border-hairline bg-ink px-4 py-2.5 text-caption font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-ink-stone"
                  >
                    {emailCodeSending ? 'Sending' : emailCodeCooldown > 0 ? `${emailCodeCooldown}s` : emailCodeSent ? 'Resend' : 'Send code'}
                  </button>
                </div>
              </div>
            )}

            {error && (
              <p
                className="rounded-md px-3 py-2 text-body-sm"
                style={{
                  background: 'var(--cg-danger-bg)',
                  color: 'var(--cg-danger)',
                  border: '1px solid var(--cg-danger-border)',
                }}
              >
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} className="cg-btn-primary w-full">
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>

          <p className="mt-6 text-center text-body-sm text-ink-steel">
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              type="button"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login');
                setRegisterRole('user');
                setAdminInviteCode('');
                setEmailCode('');
                setEmailCodeSent(false);
                setEmailCodeCooldown(0);
                setError('');
              }}
              className="font-semibold text-ink underline-offset-2 hover:underline"
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
