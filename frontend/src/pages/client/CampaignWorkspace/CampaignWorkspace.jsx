import { useState } from 'react';
import { Link, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { useToast } from '../../../contexts/ToastContext';
import clientApi from '../../../api/client';
import LoaderOverlay from '../../../components/shared/LoaderOverlay';
import CampaignHeader from '../../../components/client/CampaignHeader';
import CampaignTabs from '../../../components/client/CampaignTabs';
import {
  CampaignWorkspaceProvider,
  useCampaignWorkspace,
} from '../../../contexts/CampaignWorkspaceContext';
import LeadsTab from './LeadsTab';
import CallsTab from './CallsTab';
import AnalyticsTab from './AnalyticsTab';
import './CampaignWorkspace.css';

const CampaignWorkspaceInner = () => {
  const { showToast } = useToast();
  const { campaignId, campaign, loading, isPausing, refreshCampaign } = useCampaignWorkspace();
  const [isStartConfirmOpen, setIsStartConfirmOpen] = useState(false);

  const handleToggleState = async () => {
    if (!campaign) return;
    if (campaign.status === 'running') {
      try {
        await clientApi.patch(`/api/campaigns/${campaignId}/stop`);
        showToast('Campaign paused.', 'success');
        refreshCampaign();
      } catch (err) {
        showToast(err.customErrorMessage || 'Failed to pause campaign.', 'error');
      }
      return;
    }
    setIsStartConfirmOpen(true);
  };

  const handleConfirmStart = async () => {
    try {
      await clientApi.patch(`/api/campaigns/${campaignId}/start`);
      showToast('Campaign started.', 'success');
      setIsStartConfirmOpen(false);
      refreshCampaign();
    } catch (err) {
      showToast(err.customErrorMessage || 'Failed to start campaign.', 'error');
    }
  };

  if (loading && !campaign) {
    return <LoaderOverlay isVisible message="Loading campaign…" />;
  }

  if (!loading && !campaign) {
    return (
      <div className="cw-not-found">
        <h1>Campaign Not Found</h1>
        <Link to="/app/campaigns">Back to Campaigns</Link>
      </div>
    );
  }

  return (
    <>
      <div className="app-page cw-page">
        <CampaignHeader onToggleState={handleToggleState} />
        <CampaignTabs />
        <div className="cw-page__content">
          <Routes>
            <Route index element={<Navigate to="leads" replace />} />
            <Route path="leads" element={<LeadsTab />} />
            <Route path="calls" element={<CallsTab />} />
            <Route path="analytics" element={<AnalyticsTab />} />
            <Route path="*" element={<Navigate to="leads" replace />} />
          </Routes>
        </div>
      </div>

      {isStartConfirmOpen && (
        <div className="cw-modal">
          <div className="cw-modal__backdrop" onClick={() => setIsStartConfirmOpen(false)} />
          <div className="cw-modal__panel">
            <h3>Start Campaign</h3>
            <p>Start dialing for <strong>{campaign?.name}</strong>?</p>
            <div className="cw-modal__actions">
              <button type="button" onClick={() => setIsStartConfirmOpen(false)}>Cancel</button>
              <button type="button" className="cw-modal__primary" onClick={handleConfirmStart}>
                Start
              </button>
            </div>
          </div>
        </div>
      )}

      {isPausing && (
        <div className="cw-pausing-banner" role="status">
          Pausing — waiting for active calls to finish…
        </div>
      )}
    </>
  );
};

const CampaignWorkspace = () => {
  const { id } = useParams();
  return (
    <CampaignWorkspaceProvider campaignId={id}>
      <CampaignWorkspaceInner />
    </CampaignWorkspaceProvider>
  );
};

export default CampaignWorkspace;
