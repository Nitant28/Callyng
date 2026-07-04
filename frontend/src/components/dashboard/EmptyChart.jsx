import './Dashboard.css';

const EmptyChart = () => (
  <div className="empty-chart">
    <div className="empty-chart__icon">
      <span className="material-symbols-outlined">monitoring</span>
    </div>
    <p className="empty-chart__title">Historical analytics</p>
    <p className="empty-chart__subtitle">coming soon.</p>
  </div>
);

export default EmptyChart;
