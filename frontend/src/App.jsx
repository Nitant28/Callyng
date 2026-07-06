import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import Login from './pages/client/Login';
import ClientDashboard from './pages/client/Dashboard';
import ClientCampaigns from './pages/client/Campaigns';
import CampaignWorkspace from './pages/client/CampaignWorkspace/CampaignWorkspace';
import ClientGuard from './client/guards/ClientGuard';
import AdminGuard from './admin/guards/AdminGuard';

const MainLayout = lazy(() => import('./components/layout/MainLayout'));

import AdminLogin from './admin/pages/AdminLogin';

import AdminOverview from './admin/pages/AdminOverview';
import AdminLayout from './admin/layouts/AdminLayout';

import AdminClients from './admin/pages/AdminClients';

import AdminClientDetail from './admin/pages/AdminClientDetail';

import AdminBotConfigs from './admin/pages/AdminBotConfigs';
import AdminCalls from './admin/pages/AdminCalls';
import AdminCampaigns from './admin/pages/AdminCampaigns';
import AdminDiagnostics from './admin/pages/AdminDiagnostics';
import AdminWebhooks from './admin/pages/AdminWebhooks';
import AdminScriptConfigs from './admin/pages/AdminScriptConfigs';

import { ToastProvider } from './contexts/ToastContext';
import { AdminAuthProvider } from './admin/contexts/AdminAuthContext';
import { AdminDataProvider } from './admin/contexts/AdminDataContext';

import ClientCampaignDetail from './pages/client/CampaignDetail';

const ClientShell = ({ children }) => (
  <Suspense fallback={null}>
    <MainLayout>{children}</MainLayout>
  </Suspense>
);

function App() {
  return (
    <ToastProvider>
      <AdminAuthProvider>
        <AdminDataProvider>
        <Router>
        <Routes>
        {/* Client Routes */}
        <Route path="/login" element={<Login />} />
        <Route
          path="/app"
          element={
            <ClientGuard>
              <ClientShell>
                <ClientDashboard />
              </ClientShell>
            </ClientGuard>
          }
        />
        <Route
          path="/app/campaigns"
          element={
            <ClientGuard>
              <ClientShell>
                <ClientCampaigns />
              </ClientShell>
            </ClientGuard>
          }
        />
        <Route
          path="/app/campaigns/:id/*"
          element={
            <ClientGuard>
              <ClientShell>
                <ClientCampaignDetail />
              </ClientShell>
            </ClientGuard>
          }
        />
        <Route path="/app/leads" element={<Navigate to="/app/campaigns" replace />} />
        <Route path="/app/calls" element={<Navigate to="/app/campaigns" replace />} />
        <Route path="/app/settings" element={<Navigate to="/app" replace />} />

        {/* Admin Routes */}
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route
          path="/admin"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminOverview />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/clients"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminClients />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/clients/:id"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminClientDetail />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/bot-configs"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminBotConfigs />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/calls"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminCalls />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/campaigns"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminCampaigns />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/diagnostics"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminDiagnostics />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/webhooks"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminWebhooks />
              </AdminLayout>
            </AdminGuard>
          }
        />
        <Route
          path="/admin/script-configs"
          element={
            <AdminGuard>
              <AdminLayout>
                <AdminScriptConfigs />
              </AdminLayout>
            </AdminGuard>
          }
        />

        {/* Fallbacks */}
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<div className="p-8 text-center text-xl">404 Not Found</div>} />
      </Routes>
      </Router>
      </AdminDataProvider>
      </AdminAuthProvider>
    </ToastProvider>
  );
}

export default App;
