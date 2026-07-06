import { Navigate } from 'react-router-dom';
import { useAdminAuth } from '../contexts/AdminAuthContext';

export default function AdminGuard({ children }) {
  const { adminKey } = useAdminAuth();
  if (!adminKey) {
    return <Navigate to="/admin/login" replace />;
  }
  return children;
}
