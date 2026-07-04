const EmptyState = () => (
  <div className="cl-empty">
    <div className="cl-empty__icon">
      <span className="material-symbols-outlined">forum</span>
    </div>
    <h3 className="page-empty__title">No conversations yet</h3>
    <p className="page-empty__desc">Launch a campaign to begin recording calls. Transcripts and recordings will appear here.</p>
  </div>
);

export default EmptyState;
