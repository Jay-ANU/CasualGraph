import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiFetch, jsonRequest } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { AuthResponse, CaptchaResponse, EmailCodeResponse } from '../types/api';
import useDocumentTitle from '../utils/useDocumentTitle';

type Mode = 'login' | 'register';
type RegisterRole = 'user' | 'admin';

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
  useDocumentTitle(mode === 'login' ? 'Sign in' : 'Create account');

  const fetchCaptcha = useCallback(async () => {
    try {
      const data = await apiFetch<CaptchaResponse>('/auth/captcha');
      setCaptchaId(data.captcha_id);
      setCaptchaImage(data.image);
      setCaptchaCode('');
    } catch {
      setError('Failed to load captcha');
    }
  }, []);

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
      const data = await apiFetch<EmailCodeResponse>('/auth/email-code/send', jsonRequest('POST', {
        email,
        captcha_id: captchaId,
        captcha_code: captchaCode,
      }));
      setEmailCodeSent(true);
      setEmailCode('');
      setEmailCodeCooldown(Number(data?.cooldown_seconds || 60));
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

      const data = await apiFetch<AuthResponse>(endpoint, jsonRequest('POST', body));
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

  const switchMode = () => {
    const nextMode: Mode = mode === 'login' ? 'register' : 'login';
    setMode(nextMode);
    if (nextMode === 'register') void fetchCaptcha();
    setRegisterRole('user');
    setAdminInviteCode('');
    setEmailCode('');
    setEmailCodeSent(false);
    setEmailCodeCooldown(0);
    setError('');
  };

  return (
    <div className="px-5 pb-24 pt-14 sm:pt-20">
      <div className="mx-auto w-full max-w-[400px]">
        <h1 className="display text-display-sm sm:text-display-md">
          {mode === 'login' ? 'Sign in to CausalGraph' : 'Create your account'}
        </h1>
        <p className="mt-3 text-ink-3">
          {mode === 'login'
            ? 'Continue with your contracts and earlier questions.'
            : 'Your documents and conversations are private to your account.'}
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          {mode === 'register' && (
            <div>
              <span className="field-label" id="account-type-label">Account type</span>
              <div className="segmented w-full" role="group" aria-labelledby="account-type-label">
                {(['user', 'admin'] as const).map((role) => (
                  <button
                    key={role}
                    type="button"
                    onClick={() => setRegisterRole(role)}
                    aria-pressed={registerRole === role}
                    className="flex-1 justify-center"
                  >
                    {role === 'user' ? 'Member' : 'Administrator'}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="field-label" htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="you@company.com"
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="field-label" htmlFor="auth-username">Name</label>
              <input
                id="auth-username"
                type="text"
                autoComplete="name"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input"
                placeholder="How your name appears in the workspace"
              />
            </div>
          )}

          {mode === 'register' && registerRole === 'admin' && (
            <div>
              <label className="field-label" htmlFor="auth-invite">Admin invite code</label>
              <input
                id="auth-invite"
                type="text"
                required
                value={adminInviteCode}
                onChange={(e) => setAdminInviteCode(e.target.value.toUpperCase())}
                className="input font-mono"
                placeholder="ADM-XXXXXXXXXX"
              />
              <p className="field-hint">Ask an existing administrator to generate one. Codes expire after five minutes.</p>
            </div>
          )}

          <div>
            <label className="field-label" htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="field-label" htmlFor="auth-captcha">Image code</label>
              <div className="flex items-center gap-2">
                <input
                  id="auth-captcha"
                  type="text"
                  required
                  inputMode="numeric"
                  maxLength={4}
                  value={captchaCode}
                  onChange={(e) => setCaptchaCode(e.target.value.replace(/\D/g, ''))}
                  className="input flex-1 font-mono tracking-[0.2em]"
                  placeholder="0000"
                />
                {captchaImage && (
                  <button
                    type="button"
                    onClick={fetchCaptcha}
                    className="h-10 shrink-0 overflow-hidden rounded-lg border border-line-strong bg-white"
                    title="Load a new image"
                    aria-label="Load a new image code"
                  >
                    <img src={captchaImage} alt="Verification digits" className="h-full" />
                  </button>
                )}
                <button type="button" onClick={fetchCaptcha} className="icon-btn h-10 w-10" title="Load a new image" aria-label="Refresh image code">
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {mode === 'register' && (
            <div>
              <label className="field-label" htmlFor="auth-email-code">Email verification code</label>
              <div className="flex items-center gap-2">
                <input
                  id="auth-email-code"
                  type="text"
                  required
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={emailCode}
                  onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, ''))}
                  className="input flex-1 font-mono tracking-[0.2em]"
                  placeholder="000000"
                />
                <button
                  type="button"
                  onClick={handleSendEmailCode}
                  disabled={emailCodeSending || emailCodeCooldown > 0}
                  className="btn btn-secondary h-10 min-w-[120px] shrink-0 px-3 tabular-nums"
                >
                  {emailCodeSending ? 'Sending…' : emailCodeCooldown > 0 ? `Resend in ${emailCodeCooldown}s` : emailCodeSent ? 'Resend' : 'Send code'}
                </button>
              </div>
              <p className="field-hint">Enter the image code first, then we will email you a six-digit code.</p>
            </div>
          )}

          {error && (
            <p role="alert" className="rounded-lg border border-err-line bg-err-bg px-3 py-2.5 text-sm text-err">
              {error}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn btn-primary btn-lg w-full">
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="mt-6 text-sm text-ink-3">
          {mode === 'login' ? 'New to CausalGraph? ' : 'Already have an account? '}
          <button type="button" onClick={switchMode} className="text-link font-medium text-ink">
            {mode === 'login' ? 'Create an account' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  );
};

export default Login;
