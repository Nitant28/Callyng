import './UploadZone.css';

const UploadZone = ({
  canImport,
  isUploading,
  uploadResult,
  campaign,
  fileInputRef,
  onDragOver,
  onDrop,
  onFileBrowse,
  onBrowseClick,
  onDownloadTemplate,
  onAddManual,
}) => {
  if (!canImport) {
    return (
      <div className="cdet-upload cdet-upload--locked">
        <span className="material-symbols-outlined">lock</span>
        <p>Lead imports are locked while the campaign is active, completed, or cancelled.</p>
      </div>
    );
  }

  const schemaHint = (() => {
    const base = ['phone', 'name'];
    const fields = campaign?.bot_config?.lead_schema?.fields || [];
    const extra = fields.map((f) => f.csv_column || f.key).filter((h) => !base.includes(h?.toLowerCase()));
    return [...base, ...extra].join(', ');
  })();

  return (
    <div className="cdet-upload-wrap">
      <div
        className="cdet-upload"
        onDragOver={onDragOver}
        onDrop={onDrop}
        role="presentation"
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={onFileBrowse}
          className="cdet-upload__input"
          accept=".csv,.xlsx"
        />
        <div className="cdet-upload__icon">
          <span className="material-symbols-outlined">description</span>
        </div>
        <h3>Drop CSV here</h3>
        <p className="cdet-upload__or">or</p>
        {isUploading ? (
          <div className="cdet-upload__loading">
            <span className="material-symbols-outlined cdet-upload__spin">progress_activity</span>
            Uploading…
          </div>
        ) : (
          <div className="cdet-upload__actions">
            <button type="button" className="cdet-upload__primary" onClick={onBrowseClick}>
              Browse Files
            </button>
            <button type="button" className="cdet-upload__secondary" onClick={onDownloadTemplate}>
              Download Template
            </button>
            <button type="button" className="cdet-upload__secondary" onClick={onAddManual}>
              Add Lead Manually
            </button>
          </div>
        )}
        <div className="cdet-upload__meta">
          <span>Supports CSV, XLSX</span>
          <span>·</span>
          <span>Maximum 50,000 rows</span>
        </div>
        <p className="cdet-upload__hint">Expected columns: <strong>{schemaHint}</strong></p>
      </div>

      {uploadResult && (
        <div className={`cdet-upload__result ${uploadResult.success ? 'cdet-upload__result--ok' : 'cdet-upload__result--err'}`}>
          <p>{uploadResult.message}</p>
          {uploadResult.details && (
            <ul>
              <li>Uploaded: <strong>{uploadResult.details.leads_uploaded}</strong></li>
              <li>Duplicates skipped: <strong>{uploadResult.details.duplicates_skipped}</strong></li>
              <li>Invalid skipped: <strong>{uploadResult.details.invalid_phones}</strong></li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default UploadZone;
