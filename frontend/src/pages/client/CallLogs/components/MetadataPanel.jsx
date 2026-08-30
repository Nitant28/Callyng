import { formatCallDuration, formatCallTime, outcomeLabel } from '../../../../utils/callLogsHelpers';
import './MetadataPanel.css';

const Row = ({ label, value }) => (
  <div className="cl-meta__row">
    <span>{label}</span>
    <strong>{value ?? '—'}</strong>
  </div>
);

const MetadataPanel = ({ call, campaignName, recordingAvailable }) => (
  <div className="cl-meta">
    <h4>Metadata</h4>
    <Row label="Campaign" value={campaignName} />
    <Row label="Lead" value={call?.name || call?.leadName} />
    <Row label="Phone" value={call?.phone || call?.leadPhone} />
    <Row label="Duration" value={formatCallDuration(call?.duration_seconds ?? call?.durationSeconds)} />
    <Row label="Outcome" value={outcomeLabel(call?.outcome)} />
    <Row label="Time" value={formatCallTime(call?.created_at ?? call?.createdAt)} />
    <Row label="Recording" value={recordingAvailable ? 'Available' : 'Unavailable'} />
    {call?.session_call_id && (
      <Row label="Call ID" value={call.session_call_id.slice(0, 12) + '…'} />
    )}
  </div>
);

export default MetadataPanel;
