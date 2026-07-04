const BulkToolbar = ({ count, onExport, onDelete, onClear }) => {
  if (!count) return null;
  return (
    <div className="lead-sheet__bulk">
      <span><strong>{count}</strong> selected</span>
      <div className="lead-sheet__bulk-actions">
        <button type="button" className="lead-sheet__bulk-btn" onClick={onExport}>Export</button>
        <button type="button" className="lead-sheet__bulk-btn lead-sheet__bulk-btn--danger" onClick={onDelete}>
          Delete
        </button>
        <button type="button" className="lead-sheet__bulk-btn" onClick={onClear}>Clear</button>
      </div>
    </div>
  );
};

export default BulkToolbar;
