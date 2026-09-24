import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { apiFetch, TOKEN_STORAGE_KEY } from '../api/client';
import type { AuthUser, MeResponse } from '../types/api';

type User = AuthUser;
interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (token: string, user: User) => void;
  logout: () => void;
  isAuthenticated: boolean;
  loading: boolean;
}
const AuthContext = createContext<AuthContextType | undefined>(undefined);
// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with the provider it reads
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
interface AuthProviderProps {
  children: ReactNode;
}
const USER_STORAGE_KEY = 'user';

const normalizeUser = (raw: Partial<User>): User => ({
  ...(raw as User),
  role: (raw?.role || 'user').toString().toLowerCase(),
  plan: (raw?.plan || (raw?.role === 'admin' ? 'max' : 'free')).toString().toLowerCase(),
});

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [loading, setLoading] = useState<boolean>(() => !!localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<User | null>(() => {
    try {
      const s = localStorage.getItem(USER_STORAGE_KEY);
      if (!s) return null;
      return normalizeUser(JSON.parse(s));
    } catch {
      return null;
    }
  });
  const login = (newToken: string, userData: User) => {
    const normalizedUser = normalizeUser(userData);
    setToken(newToken);
    setUser(normalizedUser);
    setLoading(false);
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(normalizedUser));
  };
  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem('causalgraph_agent_current_session_id_v1');
    localStorage.removeItem('causalgraph_agent_selected_document_id');
    setLoading(false);
  };

  useEffect(() => {
    // Without a token there is nothing to check: `loading` starts false in that
    // case, and logout() and a failed check below both set it false themselves.
    if (!token) return;
    let cancelled = false;
    const syncCurrentUser = async () => {
      try {
        const payload = await apiFetch<MeResponse>('/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        });
        const normalizedUser = normalizeUser(payload?.user || payload);
        if (!cancelled) {
          setUser(normalizedUser);
          localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(normalizedUser));
        }
      } catch {
        if (!cancelled) {
          setToken(null);
          setUser(null);
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          localStorage.removeItem(USER_STORAGE_KEY);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    syncCurrentUser();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value: AuthContextType = {
    user,
    token,
    login,
    logout,
    isAuthenticated: !!token,
    loading,
  };
  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
