import { Navigate } from 'react-router-dom';
import { useAdminAuth } from '../../contexts/AdminAuthContext';

export const ClientGuard = ({ children }) => {
  const apiKey = localStorage.getItem('client_api_key');
  if (!apiKey) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

export const AdminGuard = ({ children }) => {
  const { adminKey } = useAdminAuth();
  if (!adminKey) {
    return <Navigate to="/admin/login" replace />;
  }
  return children;
};
