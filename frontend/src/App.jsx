import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/client/Login';
import ClientDashboard from './pages/client/Dashboard';
import ClientCampaignDetail from './pages/client/CampaignDetail';
import ClientCallLogs from './pages/client/CallLogs';
import ClientSettings from './pages/client/Settings';
import { ClientGuard, AdminGuard } from './components/shared/Guards';
import Layout from './components/shared/layout/Layout';

const AdminLogin = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Login (Coming Soon)</h1>
  </div>
);

const AdminOverview = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Overview (Coming Soon)</h1>
  </div>
);

const AdminClients = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Clients (Coming Soon)</h1>
  </div>
);

const AdminClientDetail = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Client Detail (Coming Soon)</h1>
  </div>
);

const AdminBotConfigs = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Bot Configs (Coming Soon)</h1>
  </div>
);

const AdminCalls = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text">
    <h1 className="text-2xl font-bold">Admin Global Calls (Coming Soon)</h1>
  </div>
);

import { ToastProvider } from './contexts/ToastContext';

function App() {
  return (
    <ToastProvider>
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
              <AdminOverview />
            </AdminGuard>
          }
        />
        <Route
          path="/admin/clients"
          element={
            <AdminGuard>
              <AdminClients />
            </AdminGuard>
          }
        />
        <Route
          path="/admin/clients/:id"
          element={
            <AdminGuard>
              <AdminClientDetail />
            </AdminGuard>
          }
        />
        <Route
          path="/admin/bot-configs"
          element={
            <AdminGuard>
              <AdminBotConfigs />
            </AdminGuard>
          }
        />
        <Route
          path="/admin/calls"
          element={
            <AdminGuard>
              <AdminCalls />
            </AdminGuard>
          }
        />

        {/* Fallbacks */}
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<div className="p-8 text-center text-xl">404 Not Found</div>} />
      </Routes>
      </Router>
    </ToastProvider>
  );
}

export default App;
