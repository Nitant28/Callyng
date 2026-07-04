import { NavLink, useParams } from 'react-router-dom';
import './CampaignTabs.css';

const TABS = [
  { id: 'leads', label: 'Leads', icon: 'groups' },
];

const CampaignTabs = () => {
  const { id } = useParams();

  return (
    <nav className="cw-tabs" aria-label="Campaign sections">
      <div className="cw-tabs__scroll">
        {TABS.map((tab) => (
          <NavLink
            key={tab.id}
            to={`/app/campaigns/${id}/${tab.id}`}
            className={({ isActive }) =>
              `cw-tabs__tab ${isActive ? 'cw-tabs__tab--active' : ''}`
            }
          >
            <span className="material-symbols-outlined">{tab.icon}</span>
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
};

export default CampaignTabs;
