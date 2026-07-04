import './AgentControlButton.css';

const AgentControlButton = ({
  agentActive,
  isPausing,
  isRunning,
  loading,
  canStart,
  onClick,
  compact = false,
}) => {
  const stopping = isPausing;
  const running = isRunning && !stopping;

  let label = 'Start Agent';
  let icon = 'play_arrow';
  let tone = 'start';

  if (stopping) {
    label = 'Stopping…';
    icon = 'hourglass_top';
    tone = 'stopping';
  } else if (running) {
    label = 'Stop Agent';
    icon = 'stop';
    tone = 'stop';
  }

  const disabled = loading || stopping || (!agentActive && !canStart);

  return (
    <button
      type="button"
      className={`agent-ctrl agent-ctrl--${tone} ${compact ? 'agent-ctrl--compact' : ''} ${running ? 'agent-ctrl--live' : ''}`}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={agentActive}
      title={disabled && !agentActive ? 'Upload leads to a draft or paused campaign first' : undefined}
    >
      {running && <span className="agent-ctrl__pulse" aria-hidden />}
      <span className="material-symbols-outlined agent-ctrl__icon">{icon}</span>
      <span className="agent-ctrl__label">{label}</span>
    </button>
  );
};

export default AgentControlButton;
