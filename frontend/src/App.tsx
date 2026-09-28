import { useI18n } from './i18n/useI18n';
import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import LocaleProvider from './i18n/LocaleProvider';
import Home from './pages/Home';
import Login from './pages/Login';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import useDocumentTitle from './utils/useDocumentTitle';

// Keep graph, research and admin bundles off the legal landing page.
const CausalInference = lazy(() => import('./pages/CausalInference'));
const Agent = lazy(() => import('./pages/Agent'));
const About = lazy(() => import('./pages/About'));
const EsgDemo = lazy(() => import('./pages/EsgDemo'));
const Admin = lazy(() => import('./pages/Admin'));
const DesktopDownload = lazy(() => import('./pages/DesktopDownload'));
const MaxMemberships = lazy(() => import('./pages/MaxMemberships'));
const ContractReview = lazy(() => import('./pages/ContractReview'));
const Recruitment = lazy(() => import('./pages/Recruitment'));
const OfferView = lazy(() => import('./pages/OfferView'));

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
  const { t } = useI18n();
  useDocumentTitle(t('Page not found'));
  return (
    <div className="mx-auto max-w-content px-5 py-32 sm:px-8">
      <p className="font-mono text-sm text-ink-4">404</p>
      <h1 className="display mt-3 text-display-md">{t("This page doesn’t exist.")}</h1>
      <p className="mt-4 text-ink-3">{t("The link may be out of date.")}{' '}<Link to="/" className="text-link text-ink">{t("Go to the homepage")}</Link>.
      </p>
    </div>
  );
};

// The research desk is a full-height application with its own navigation, and a
// candidate's offer page stands on its own, so the marketing header is only
// rendered on the other routes.
const Shell: React.FC = () => {
  const { t } = useI18n();
  const location = useLocation();
  const isWorkspace = ['/agent', '/research', '/legal'].includes(location.pathname);
  const isOfferPage = location.pathname.startsWith('/offer/');
  return (
    <div className="min-h-screen bg-paper">
      {!isWorkspace && !isOfferPage && <Navbar />}
      <main>
        <Suspense fallback={isOfferPage ? <div className="min-h-screen" style={{ background: '#FBFAF8' }} /> : <p role="status" className="px-6 py-12 text-sm text-ink-3">{t('加载中…')}</p>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/home" element={<Home />} />
            <Route path="/zh" element={<Home />} />
            <Route path="/en" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/esg-demo" element={<EsgDemo />} />
            <Route path="/causal-inference" element={<CausalInference />} />
            <Route path="/desktop" element={<DesktopDownload />} />
            <Route path="/download" element={<DesktopDownload />} />
            <Route path="/agent" element={<ProtectedRoute><Agent /></ProtectedRoute>} />
            <Route path="/research" element={<ProtectedRoute><Agent /></ProtectedRoute>} />
            <Route path="/legal" element={<ProtectedRoute><ContractReview /></ProtectedRoute>} />
            <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
            <Route path="/admin/memberships" element={<AdminRoute><MaxMemberships /></AdminRoute>} />
            <Route path="/admin/recruitment" element={<AdminRoute><Recruitment /></AdminRoute>} />
            <Route path="/offer/:token" element={<OfferView />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LocaleProvider><Shell /></LocaleProvider>
      </Router>
    </AuthProvider>
  );
}
export default App;
