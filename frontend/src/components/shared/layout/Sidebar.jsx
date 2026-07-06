import { Link, useLocation } from 'react-router-dom';
import { SIDEBAR_NAV } from '../../../constants/sidebar';
import { useDashboardData } from '../../../contexts/DashboardDataContext';

const formatCredits = (value) => {
  if (value == null) return '0';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
};

const Sidebar = ({ onSignOut, isOpen = false }) => {
  const location = useLocation();
  const path = location.pathname;
  const { credits, loading } = useDashboardData();
  
  // Try mapping balanceCredits or balance_credits
  const balance = credits?.balanceCredits ?? credits?.balance_credits ?? null;

  return (
    <aside className={`cl-sidebar ${isOpen ? 'cl-sidebar--open' : ''}`}>
      {/* Brand */}
      <div className="cl-sidebar__logo">
        <div className="cl-sidebar__brand">Dev Client</div>
        <div className="cl-sidebar__subtitle">AI Voice Platform</div>
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
          <div style={{ height: '24px', width: '80px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
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
