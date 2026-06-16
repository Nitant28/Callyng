import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/client/Login';
import ClientDashboard from './pages/client/Dashboard';
import ClientCampaignDetail from './pages/client/CampaignDetail';
import ClientCallLogs from './pages/client/CallLogs';
import ClientSettings from './pages/client/Settings';
import { ClientGuard, AdminGuard } from './components/shared/Guards';
import Layout from './components/shared/layout/Layout';

import AdminLogin from './pages/admin/AdminLogin';

import AdminOverview from './pages/admin/AdminOverview';
import AdminLayout from './components/shared/layout/AdminLayout';

import AdminClients from './pages/admin/AdminClients';

import AdminClientDetail from './pages/admin/AdminClientDetail';

import AdminBotConfigs from './pages/admin/AdminBotConfigs';
import AdminCalls from './pages/admin/AdminCalls';
import AdminCampaigns from './pages/admin/AdminCampaigns';
import AdminDiagnostics from './pages/admin/AdminDiagnostics';
import AdminWebhooks from './pages/admin/AdminWebhooks';
import AdminScriptConfigs from './pages/admin/AdminScriptConfigs';

import { ToastProvider } from './contexts/ToastContext';
import { AdminAuthProvider } from './contexts/AdminAuthContext';
import { AdminDataProvider } from './contexts/AdminDataContext';

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
              <Layout>
                <ClientDashboard />
              </Layout>
            </ClientGuard>
          }
        />
        <Route
          path="/app/campaigns/:id"
          element={
            <ClientGuard>
              <Layout>
                <ClientCampaignDetail />
              </Layout>
            </ClientGuard>
          }
        />
        <Route
          path="/app/calls"
          element={
            <ClientGuard>
              <Layout>
                <ClientCallLogs />
              </Layout>
            </ClientGuard>
          }
        />
        <Route
          path="/app/settings"
          element={
            <ClientGuard>
              <Layout>
                <ClientSettings />
              </Layout>
            </ClientGuard>
          }
        />

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
