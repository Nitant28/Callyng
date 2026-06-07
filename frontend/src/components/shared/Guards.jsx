import { Navigate } from 'react-router-dom';

export const ClientGuard = ({ children }) => {
  const apiKey = localStorage.getItem('client_api_key');
  if (!apiKey) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

export const AdminGuard = ({ children }) => {
  const apiKey = localStorage.getItem('admin_api_key');
  if (!apiKey) {
    return <Navigate to="/admin/login" replace />;
  }
  return children;
};
