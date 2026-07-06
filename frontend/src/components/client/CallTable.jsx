import {
  formatCallDuration,
  formatCallTime,
  outcomeLabel,
  outcomeTone,
} from '../../utils/callLogsHelpers';
import { Badge } from '../enterprise';
import './CallTable.css';

const CallTable = ({ calls = [], loading = false, onOpen, onTranscript }) => (
  <div className="cw-call-table-wrap">
    <table className="cw-call-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Phone</th>
          <th>Duration</th>
          <th>Outcome</th>
          <th>Timestamp</th>
          <th>Recording</th>
          <th>Transcript</th>
        </tr>
      </thead>
      <tbody>
        {loading && (
          <tr>
            <td colSpan={7} className="cw-call-table__empty">Loading calls…</td>
          </tr>
        )}
        {!loading && calls.length === 0 && (
          <tr>
            <td colSpan={7} className="cw-call-table__empty">No calls yet for this campaign.</td>
          </tr>
        )}
        {!loading &&
          calls.map((call) => (
            <tr
              key={call.sessionCallId}
              className="cw-call-table__row"
              onClick={() => onOpen?.(call)}
            >
              <td>{call.leadName}</td>
              <td className="cw-call-table__mono">{call.leadPhone}</td>
              <td>{formatCallDuration(call.durationSeconds)}</td>
              <td>
                <Badge tone={outcomeTone(call.outcome)}>
                  {call.inProgress ? 'Live' : outcomeLabel(call.outcome)}
                </Badge>
              </td>
              <td className="cw-call-table__muted">{formatCallTime(call.createdAt)}</td>
              <td onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="cw-call-table__icon-btn"
                  onClick={() => onOpen?.(call)}
                  aria-label="Play recording"
                >
                  <span className="material-symbols-outlined">play_circle</span>
                </button>
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="cw-call-table__icon-btn"
                  onClick={() => onTranscript?.(call)}
                  aria-label="View transcript"
                >
                  <span className="material-symbols-outlined">description</span>
                </button>
              </td>
            </tr>
          ))}
      </tbody>
    </table>
  </div>
);

export default CallTable;
