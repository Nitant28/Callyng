import './DashboardScopeTabs.css';

const DashboardScopeTabs = ({ tabs, activeId, onChange }) => (
  <div className="cl-scope-tabs" role="tablist" aria-label="Dashboard scope">
    <div className="cl-scope-tabs__scroll">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeId === tab.id}
          className={`cl-scope-tabs__tab${activeId === tab.id ? ' cl-scope-tabs__tab--active' : ''}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.live ? <span className="cl-scope-tabs__live" aria-hidden /> : null}
        </button>
      ))}
    </div>
  </div>
);

export default DashboardScopeTabs;
