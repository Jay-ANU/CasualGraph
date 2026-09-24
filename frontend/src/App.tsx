import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import Agent from './pages/Agent';
import Login from './pages/Login';
import Admin from './pages/Admin';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import useDocumentTitle from './utils/useDocumentTitle';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace state={{ from: location }} />;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location }} />;
  return (user?.role || '').toLowerCase() === 'admin' ? <>{children}</> : <Navigate to="/agent" replace />;
};

const NotFound: React.FC = () => {
  useDocumentTitle('Page not found');
  return (
    <div className="mx-auto max-w-content px-5 py-32 sm:px-8">
      <p className="font-mono text-sm text-ink-4">404</p>
      <h1 className="display mt-3 text-display-md">This page doesn’t exist.</h1>
      <p className="mt-4 text-ink-3">
        The link may be out of date. <Link to="/" className="text-link text-ink">Go to the homepage</Link>.
      </p>
    </div>
  );
};

// The workspace is a full-height application with its own navigation, so the
// site header is only rendered on the other routes.
const Shell: React.FC = () => {
  const location = useLocation();
  const isWorkspace = location.pathname === '/agent';
  return (
    <div className="min-h-screen bg-paper">
      {!isWorkspace && <Navbar />}
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/home" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/agent" element={<ProtectedRoute><Agent /></ProtectedRoute>} />
          <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Shell />
      </Router>
    </AuthProvider>
  );
}
export default App;
