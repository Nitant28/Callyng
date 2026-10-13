import { Link, useLocation } from 'react-router-dom';
import SwarnaLogo from '../../components/brand/SwarnaLogo';

const Sidebar = ({ handleSignOut, balance = null }) => {
  const location = useLocation();
  const path = location.pathname;

  const isDashboard = path === '/app' || (!path.startsWith('/app/calls') && !path.startsWith('/app/settings') && !path.startsWith('/app/campaigns'));
  const isCampaigns = path.startsWith('/app/campaigns');

  return (
    <aside className="cl-sidebar">
      <div className="cl-sidebar__logo">
        <SwarnaLogo variant="dark" size="sm" />
      </div>

      <nav className="cl-sidebar__nav" aria-label="Main navigation">
        <Link
          to="/app"
          className={`cl-sidebar__item${isDashboard ? ' active' : ''}`}
          aria-current={isDashboard ? 'page' : undefined}
        >
          <span className="material-symbols-outlined">dashboard</span>
          <span>{isDashboard ? <strong>Dashboard</strong> : 'Dashboard'}</span>
        </Link>

        <Link
          to="/app/campaigns"
          className={`cl-sidebar__item${isCampaigns ? ' active' : ''}`}
          aria-current={isCampaigns ? 'page' : undefined}
        >
          <span className="material-symbols-outlined">campaign</span>
          <span>{isCampaigns ? <strong>Campaigns</strong> : 'Campaigns'}</span>
        </Link>
      </nav>

      <div className="cl-sidebar__footer">
        {balance !== null && (
          <div className="cl-sidebar__credits">
            <div className="cl-sidebar__credits-label">Credits remaining</div>
            <div className="cl-sidebar__credits-value">
              {Number(balance).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              <span style={{ fontSize: '12px', fontWeight: 500, color: '#7A9388', marginLeft: '6px' }}>/ 10,000</span>
            </div>
            <div className="cl-progress-bar">
              <div
                className="cl-progress-bar__fill"
                style={{ width: `${Math.min((balance / 10000) * 100, 100)}%` }}
              />
            </div>
            <div className="cl-sidebar__credits-sub">Prepaid balance</div>
          </div>
        )}

        <button
          onClick={handleSignOut}
          className="cl-btn cl-btn--ghost cl-sidebar__signout"
          type="button"
        >
          <span className="material-symbols-outlined">logout</span>
          Sign Out
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
