import { Link, useLocation } from 'react-router-dom';
import { SIDEBAR_NAV } from '../../../constants/sidebar';
import { useDashboardData } from '../../../contexts/DashboardDataContext';
import SwarnaLogo from '../../brand/SwarnaLogo';

const formatCredits = (value) => {
  if (value == null) return '0';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
};

const Sidebar = ({ onSignOut, isOpen = false }) => {
  const location = useLocation();
  const path = location.pathname;
  const { balance: creditsData, loading } = useDashboardData();
  
  // Try mapping balanceCredits or balance_credits
  const balance = creditsData?.balanceCredits ?? creditsData?.balance_credits ?? null;

  return (
    <aside className={`cl-sidebar ${isOpen ? 'cl-sidebar--open' : ''}`}>
      <div className="cl-sidebar__logo">
        <Link to="/app" className="cl-sidebar__logo-link" aria-label="Swarna home">
          <SwarnaLogo variant="dark" size="md" />
        </Link>
      </div>

      {/* Navigation */}
      <nav className="cl-sidebar__nav" aria-label="Main navigation">
        {SIDEBAR_NAV.map((item) => {
          const isActive = item.match(path);
          return (
            <Link
              key={item.id}
              to={item.path}
              className={`cl-sidebar__item ${isActive ? 'active' : ''}`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Credits Display */}
      <div className="cl-sidebar__credits">
        <div className="cl-sidebar__credits-label">Credits Remaining</div>
        {loading && balance == null ? (
          <div style={{ height: '24px', width: '80px', background: '#D1FAE5', borderRadius: '8px', animation: 'pulse 1.5s infinite' }} />
        ) : (
          <div className="cl-sidebar__credits-value">₹{formatCredits(balance)}</div>
        )}
        <div className="cl-sidebar__credits-sub">Prepaid balance</div>
      </div>

      {/* Sign Out */}
      <div className="cl-sidebar__footer">
        <button
          type="button"
          className="cl-sidebar__item"
          onClick={onSignOut}
        >
          <span className="material-symbols-outlined">logout</span>
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
