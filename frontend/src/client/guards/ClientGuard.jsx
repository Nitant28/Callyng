import { Navigate } from 'react-router-dom';

export default function ClientGuard({ children }) {
  const apiKey = localStorage.getItem('client_api_key');
  if (!apiKey) {
    return <Navigate to="/login" replace />;
  }
  return children;
}
