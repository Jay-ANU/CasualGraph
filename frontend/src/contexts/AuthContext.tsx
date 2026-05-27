import React, { createContext, useContext, useEffect, useMemo, useState, ReactNode } from 'react';
interface User {
  id: string;
  email: string;
  username: string;
  role?: string;
  plan?: string;
  plan_label?: string;
  points_limit?: number | null;
  unlimited?: boolean;
  created_at?: string;
}
interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (token: string, user: User) => void;
  logout: () => void;
  isAuthenticated: boolean;
  loading: boolean;
}
const AuthContext = createContext<AuthContextType | undefined>(undefined);
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
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState<boolean>(() => !!localStorage.getItem('token'));
  const [user, setUser] = useState<User | null>(() => {
    try {
      const s = localStorage.getItem('user');
      if (!s) return null;
      const parsed = JSON.parse(s);
      return {
        ...parsed,
        role: (parsed?.role || 'user').toString().toLowerCase(),
        plan: (parsed?.plan || (parsed?.role === 'admin' ? 'max' : 'free')).toString().toLowerCase(),
      };
    } catch {
      return null;
    }
  });
  const login = (newToken: string, userData: User) => {
    const normalizedUser: User = {
      ...userData,
      role: (userData?.role || 'user').toString().toLowerCase(),
      plan: (userData?.plan || (userData?.role === 'admin' ? 'max' : 'free')).toString().toLowerCase(),
    };
    setToken(newToken);
    setUser(normalizedUser);
    setLoading(false);
    localStorage.setItem('token', newToken);
    localStorage.setItem('user', JSON.stringify(normalizedUser));
  };
  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('causalgraph_agent_current_session_id_v1');
    localStorage.removeItem('causalgraph_agent_selected_document_id');
    setLoading(false);
  };

  const apiBase = useMemo(() => {
    const host = window.location.hostname || '127.0.0.1';
    const localApiHost = host === 'localhost' || host === '127.0.0.1';
    return process.env.REACT_APP_ESG_API_BASE || (localApiHost ? `http://${host}:8000` : '');
  }, []);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const syncCurrentUser = async () => {
      try {
        const response = await fetch(`${apiBase}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error('auth_sync_failed');
        const payload = await response.json();
        const serverUser = payload?.user || payload;
        const normalizedUser: User = {
          ...serverUser,
          role: (serverUser?.role || 'user').toString().toLowerCase(),
          plan: (serverUser?.plan || (serverUser?.role === 'admin' ? 'max' : 'free')).toString().toLowerCase(),
        };
        if (!cancelled) {
          setUser(normalizedUser);
          localStorage.setItem('user', JSON.stringify(normalizedUser));
        }
      } catch {
        if (!cancelled) {
          setToken(null);
          setUser(null);
          localStorage.removeItem('token');
          localStorage.removeItem('user');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    syncCurrentUser();
    return () => {
      cancelled = true;
    };
  }, [apiBase, token]);

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
