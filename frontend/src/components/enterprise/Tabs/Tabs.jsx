import './Tabs.css';

const Tabs = ({ tabs, value, onChange }) => (
  <div className="ent-tabs" role="tablist">
    {tabs.map((tab) => (
      <button
        key={tab.id}
        type="button"
        role="tab"
        aria-selected={value === tab.id}
        className={`ent-tabs__tab ${value === tab.id ? 'ent-tabs__tab--active' : ''}`}
        onClick={() => onChange(tab.id)}
      >
        {tab.label}
        {tab.count != null && <span className="ent-tabs__count">{tab.count}</span>}
      </button>
    ))}
  </div>
);

export default Tabs;
