import './CampaignEmpty.css';

const CampaignEmpty = ({ activeTab }) => (
  <div className="cmp-empty">
    <div className="cmp-empty__icon">
      <span className="material-symbols-outlined">campaign</span>
    </div>
    <h3 className="cl-card-title page-empty__title">
      {activeTab === 'all' ? 'No campaigns yet' : `No ${activeTab} campaigns`}
    </h3>
    <p className="cl-body page-empty__desc">Contact your administrator to create campaigns.</p>
  </div>
);

export default CampaignEmpty;
