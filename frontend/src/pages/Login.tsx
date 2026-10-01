import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiFetch, jsonRequest } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../i18n/core';
import type { AuthResponse, CaptchaResponse, EmailCodeResponse } from '../types/api';
import useDocumentTitle from '../utils/useDocumentTitle';

type Mode = 'login' | 'register';
type RegisterRole = 'user' | 'admin';
/** Messages written on this page carry both languages so they follow the switch; the server's own are shown as received. */
type ErrorMessage = string | { zh: string; en: string };

const Login: React.FC = () => {
  const { login } = useAuth();
  const { tx } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<ErrorMessage>('');
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
  useDocumentTitle(mode === 'login' ? tx('登录', 'Sign in') : tx('创建账户', 'Create account'));
  const errorText = typeof error === 'string' ? error : tx(error.zh, error.en);

  const fetchCaptcha = useCallback(async () => {
    try {
      const data = await apiFetch<CaptchaResponse>('/auth/captcha');
      setCaptchaId(data.captcha_id);
      setCaptchaImage(data.image);
      setCaptchaCode('');
    } catch {
      setError({ zh: '图形验证码加载失败', en: 'Failed to load captcha' });
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
      setError({ zh: '请先填写邮箱', en: 'Enter your email first' });
      return;
    }
    if (!captchaId || !captchaCode.trim()) {
      setError({ zh: '发送邮箱验证码前，请先填写图形验证码', en: 'Enter the image captcha before sending the email code' });
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
      setError(err instanceof Error ? err.message : { zh: '邮箱验证码发送失败', en: 'Unable to send email code' });
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
          : '/legal';
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : { zh: '出了点问题，请稍后再试', en: 'Something went wrong' });
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
          {mode === 'login' ? tx('登录 CausalGraph', 'Sign in to CausalGraph') : tx('创建你的账户', 'Create your account')}
        </h1>
        <p className="mt-3 text-ink-3">
          {mode === 'login'
            ? tx('继续处理你的合同，查看之前的提问。', 'Continue with your contracts and earlier questions.')
            : tx('你的文档和对话仅你本人可见。', 'Your documents and conversations are private to your account.')}
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          {mode === 'register' && (
            <div>
              <span className="field-label" id="account-type-label">{tx('账户类型', 'Account type')}</span>
              <div className="segmented w-full" role="group" aria-labelledby="account-type-label">
                {(['user', 'admin'] as const).map((role) => (
                  <button
                    key={role}
                    type="button"
                    onClick={() => setRegisterRole(role)}
                    aria-pressed={registerRole === role}
                    className="flex-1 justify-center"
                  >
                    {role === 'user' ? tx('普通用户', 'Member') : tx('管理员', 'Administrator')}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="field-label" htmlFor="auth-email">{tx('邮箱', 'Email')}</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder={tx('name@company.com', 'you@company.com')}
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="field-label" htmlFor="auth-username">{tx('姓名', 'Name')}</label>
              <input
                id="auth-username"
                type="text"
                autoComplete="name"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input"
                placeholder={tx('在工作区中显示的名字', 'How your name appears in the workspace')}
              />
            </div>
          )}

          {mode === 'register' && registerRole === 'admin' && (
            <div>
              <label className="field-label" htmlFor="auth-invite">{tx('管理员邀请码', 'Admin invite code')}</label>
              <input
                id="auth-invite"
                type="text"
                required
                value={adminInviteCode}
                onChange={(e) => setAdminInviteCode(e.target.value.toUpperCase())}
                className="input font-mono"
                placeholder="ADM-XXXXXXXXXX"
              />
              <p className="field-hint">
                {tx('请联系现有管理员生成邀请码，邀请码 5 分钟内有效。', 'Ask an existing administrator to generate one. Codes expire after five minutes.')}
              </p>
            </div>
          )}

          <div>
            <label className="field-label" htmlFor="auth-password">{tx('密码', 'Password')}</label>
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
              <label className="field-label" htmlFor="auth-captcha">{tx('图形验证码', 'Image code')}</label>
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
                    title={tx('看不清？换一张', 'Load a new image')}
                    aria-label={tx('换一张图形验证码', 'Load a new image code')}
                  >
                    <img src={captchaImage} alt={tx('验证码数字', 'Verification digits')} className="h-full" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={fetchCaptcha}
                  className="icon-btn h-10 w-10"
                  title={tx('看不清？换一张', 'Load a new image')}
                  aria-label={tx('刷新图形验证码', 'Refresh image code')}
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {mode === 'register' && (
            <div>
              <label className="field-label" htmlFor="auth-email-code">{tx('邮箱验证码', 'Email verification code')}</label>
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
                  {emailCodeSending
                    ? tx('发送中…', 'Sending…')
                    : emailCodeCooldown > 0
                      ? tx(`${emailCodeCooldown} 秒后重发`, `Resend in ${emailCodeCooldown}s`)
                      : emailCodeSent
                        ? tx('重新发送', 'Resend')
                        : tx('发送验证码', 'Send code')}
                </button>
              </div>
              <p className="field-hint">
                {tx('请先填写图形验证码，我们会向你的邮箱发送 6 位验证码。', 'Enter the image code first, then we will email you a six-digit code.')}
              </p>
            </div>
          )}

          {errorText && (
            <p role="alert" className="rounded-lg border border-err-line bg-err-bg px-3 py-2.5 text-sm text-err">
              {errorText}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn btn-primary btn-lg w-full">
            {loading ? tx('请稍候…', 'Please wait…') : mode === 'login' ? tx('登录', 'Sign in') : tx('创建账户', 'Create account')}
          </button>
        </form>

        <p className="mt-6 text-sm text-ink-3">
          {mode === 'login' ? tx('初次使用 CausalGraph？', 'New to CausalGraph? ') : tx('已有账户？', 'Already have an account? ')}
          <button type="button" onClick={switchMode} className="text-link font-medium text-ink">
            {mode === 'login' ? tx('创建账户', 'Create an account') : tx('登录', 'Sign in')}
          </button>
        </p>
      </div>
    </div>
  );
};

export default Login;
