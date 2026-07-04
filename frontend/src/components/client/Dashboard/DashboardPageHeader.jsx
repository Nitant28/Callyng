import './DashboardPageHeader.css';

const DashboardPageHeader = ({ clientName }) => {
  const name = clientName || 'Client';

  return (
    <header className="dashboard-header">
      <h1 className="dashboard-header__title">Welcome Back, {name}</h1>
    </header>
  );
};

export default DashboardPageHeader;
