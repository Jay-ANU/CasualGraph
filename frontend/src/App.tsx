import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import CausalInference from './pages/CausalInference';
import Agent from './pages/Agent';
import About from './pages/About';
import EsgDemo from './pages/EsgDemo';
import Login from './pages/Login';
import Admin from './pages/Admin';
import DesktopDownload from './pages/DesktopDownload';
import { AuthProvider, useAuth } from './contexts/AuthContext';

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

function App() {
  return (
    <AuthProvider>
      <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <div className="min-h-screen bg-canvas">
          <Navbar />
          <main>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/home" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/esg-demo" element={<EsgDemo />} />
              <Route path="/causal-inference" element={<CausalInference />} />
              <Route path="/desktop" element={<DesktopDownload />} />
              <Route path="/download" element={<DesktopDownload />} />
              <Route path="/agent" element={<ProtectedRoute><Agent /></ProtectedRoute>} />
              <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
              <Route path="/about" element={<About />} />
            </Routes>
          </main>
        </div>
      </Router>
    </AuthProvider>
  );
}
export default App;
