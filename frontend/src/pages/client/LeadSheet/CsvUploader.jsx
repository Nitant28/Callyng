import { useRef, useState, useEffect } from 'react';
import { Progress, Button } from '../../../components/enterprise';
import { campaignLabel, canImportToCampaign, parseLeadApiError } from './leadUtils';
import leadService from '../../../services/leadService';
import './CsvUploader.css';

const STEPS = ['Reading', 'Validating', 'Importing', 'Done'];
const EXPECTED = ['Name', 'Phone', 'Email', 'Company', 'Notes'];

const CsvUploader = ({ open, campaigns, defaultCampaignId, onClose, onUpload, onSuccess }) => {
  const inputRef = useRef(null);
  const [campaignId, setCampaignId] = useState('');
  const [dragging, setDragging] = useState(false);
  const [step, setStep] = useState(-1);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCampaignId(defaultCampaignId || '');
    setStep(-1);
    setProgress(0);
    setResult(null);
    setError(null);
  }, [open, defaultCampaignId]);

  if (!open) return null;

  const importable = (campaigns || []).filter(canImportToCampaign);
  const selectedCampaign = (campaigns || []).find((c) => c.id === campaignId);
  const canUpload = campaignId && canImportToCampaign(selectedCampaign);

  const resetProgress = () => {
    setStep(-1);
    setProgress(0);
    setResult(null);
    setError(null);
  };

  const runUpload = async (file) => {
    if (!campaignId) {
      setError('Select a campaign first.');
      return;
    }
    if (!canUpload) {
      setError('Imports are locked while this campaign is running, completed, or cancelled. Pause it first.');
      return;
    }
    if (!file) return;

    const ext = (file.name || '').toLowerCase();
    if (!ext.endsWith('.csv') && !ext.endsWith('.xlsx')) {
      setError('Please upload a CSV or XLSX file.');
      return;
    }

    setError(null);
    setResult(null);
    setStep(0);
    setProgress(15);

    try {
      setStep(1);
      setProgress(40);
      await new Promise((r) => setTimeout(r, 200));
      setStep(2);
      setProgress(65);
      const data = await onUpload(campaignId, file, (evt) => {
        if (evt.total) setProgress(65 + Math.round((evt.loaded / evt.total) * 30));
      });
      setStep(3);
      setProgress(100);
      const imported = data.leads_uploaded ?? data.imported ?? 0;
      setResult({
        imported,
        duplicates: data.duplicates_skipped ?? data.duplicates ?? 0,
        failed: data.invalid_phones ?? data.failed ?? 0,
      });
      onSuccess?.({ campaignId, imported, data });
    } catch (err) {
      setError(parseLeadApiError(err));
      setStep(-1);
      setProgress(0);
    }
  };

  const onFiles = (files) => {
    const file = files?.[0];
    if (file) runUpload(file);
  };

  const handleDownloadTemplate = async () => {
    if (!campaignId) {
      setError('Select a campaign to download its template.');
      return;
    }
    setDownloading(true);
    setError(null);
    try {
      const blob = await leadService.downloadTemplate(campaignId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `leads-template-${campaignId.slice(0, 8)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(parseLeadApiError(err));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="ls-upload__backdrop" onClick={onClose} role="presentation">
      <div className="ls-upload" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="ls-upload__header">
          <h2>Import leads</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="ls-upload__body">
          <label className="ls-upload__campaign">
            Campaign
            <select
              value={campaignId}
              onChange={(e) => { setCampaignId(e.target.value); resetProgress(); }}
            >
              <option value="">Select campaign…</option>
              {(campaigns || []).map((c) => (
                <option key={c.id} value={c.id} disabled={!canImportToCampaign(c)}>
                  {campaignLabel(c)}{!canImportToCampaign(c) ? ' (locked)' : ''}
                </option>
              ))}
            </select>
          </label>

          {importable.length === 0 && (
            <p className="ls-upload__warn">
              No importable campaigns. Create a draft campaign or pause a running one first.
            </p>
          )}

          {campaignId && !canUpload && (
            <p className="ls-upload__warn">
              This campaign cannot accept imports while active. Pause it from Campaigns.
            </p>
          )}

          <div
            className={`ls-upload__drop ${dragging ? 'ls-upload__drop--active' : ''} ${!canUpload ? 'ls-upload__drop--disabled' : ''}`}
            onDragOver={(e) => { if (!canUpload) return; e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { if (!canUpload) return; e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx"
              className="ls-upload__input"
              onChange={(e) => { onFiles(e.target.files); e.target.value = ''; }}
            />
            <span className="material-symbols-outlined">cloud_upload</span>
            <p>Drop CSV here</p>
            <span className="ls-upload__or">or</span>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={!canUpload || (step >= 0 && step < 3)}
            >
              Browse Files
            </button>
          </div>

          <div className="ls-upload__cols">
            <p>Expected columns</p>
            <ul>
              {EXPECTED.map((col) => (
                <li key={col}><span className="material-symbols-outlined">check</span>{col}</li>
              ))}
            </ul>
          </div>

          <div className="ls-upload__template-row">
            <Button
              variant="secondary"
              size="sm"
              loading={downloading}
              disabled={!campaignId}
              onClick={handleDownloadTemplate}
            >
              Download template
            </Button>
          </div>

          {step >= 0 && (
            <div className="ls-upload__progress">
              <p>{STEPS[step]}…</p>
              <Progress value={progress} />
            </div>
          )}

          {result && (
            <div className="ls-upload__result">
              <strong>{result.imported.toLocaleString('en-IN')} leads imported</strong>
              {(result.duplicates > 0 || result.failed > 0) && (
                <span>
                  {result.duplicates > 0 && `${result.duplicates} duplicates skipped`}
                  {result.duplicates > 0 && result.failed > 0 && ' · '}
                  {result.failed > 0 && `${result.failed} invalid rows`}
                </span>
              )}
            </div>
          )}

          {error && <p className="ls-upload__error">{error}</p>}

          {result && (
            <footer className="ls-upload__footer">
              <Button variant="primary" onClick={onClose}>Done</Button>
            </footer>
          )}
        </div>
      </div>
    </div>
  );
};

export default CsvUploader;
