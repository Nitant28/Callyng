import { useState } from 'react';
import DateRangeDropdown from './DateRangeDropdown';
import './Dashboard.css';

const DashboardHeader = ({ clientName, selectedRange: controlledRange, onRangeChange }) => {
  const [internalRange, setInternalRange] = useState('last7');
  const selectedRange = controlledRange ?? internalRange;
  const displayName = clientName || 'Client';

  const handleRangeChange = (range) => {
    if (controlledRange === undefined) {
      setInternalRange(range);
    }
    onRangeChange?.(range);
  };

  return (
    <header className="dashboard-header ds-enter ds-enter-1">
      <div className="dashboard-header__copy">
        <h1 className="dashboard-header__greeting">
          Good morning,
          <br />
          {displayName} 👋
        </h1>
        <p className="dashboard-header__subtitle">
          Here&apos;s what&apos;s happening with your campaigns today.
        </p>
      </div>
      <DateRangeDropdown value={selectedRange} onChange={handleRangeChange} />
    </header>
  );
};

export default DashboardHeader;
