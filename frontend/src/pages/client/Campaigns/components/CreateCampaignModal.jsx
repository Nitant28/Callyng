import { useState } from 'react';
import { Button, Modal } from '../../../../components/enterprise';
import './CreateCampaignModal.css';

const defaultForm = {
  name: '',
  bot_config_id: '',
  file: null,
};

const CreateCampaignModal = ({ open, onClose, botOptions, onSubmit, submitting }) => {
  const [form, setForm] = useState(defaultForm);
  const [error, setError] = useState(null);

  const reset = () => {
    setForm(defaultForm);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const update = (patch) => setForm((f) => ({ ...f, ...patch }));

  const validate = () => {
    if (!form.name.trim()) return 'Campaign name is required.';
    if (!form.bot_config_id) return 'Select a voice agent.';
    return null;
  };

  const handleSubmit = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    try {
      await onSubmit(form);
      reset();
    } catch (err) {
      setError(err.customErrorMessage || err.message || 'Failed to create campaign.');
    }
  };

  const footer = (
    <>
      <Button variant="ghost" onClick={handleClose}>Cancel</Button>
      <Button variant="primary" loading={submitting} onClick={handleSubmit}>
        Create Campaign
      </Button>
    </>
  );

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="New Campaign"
      subtitle="Set up your campaign name, voice agent, and optional leads file."
      icon="campaign"
      footer={footer}
      width={560}
    >
      {error && <p className="cmp-create__error">{error}</p>}

      <div className="cmp-create">
        <section className="cmp-create__section">
          <h3 className="cmp-create__section-title">
            <span className="cmp-create__section-num">1</span>
            <span>Details</span>
          </h3>
          <div className="ent-form">
            <label>
              Campaign name
              <input
                value={form.name}
                onChange={(e) => update({ name: e.target.value })}
                placeholder="Healthcare Outreach"
              />
            </label>
          </div>
        </section>

        <section className="cmp-create__section">
          <h3 className="cmp-create__section-title">
            <span className="cmp-create__section-num">2</span>
            <span>Voice Agent</span>
          </h3>
          <div className="ent-form">
            <label>
              Voice agent
              <select
                value={form.bot_config_id}
                onChange={(e) => update({ bot_config_id: e.target.value })}
              >
                <option value="">Select agent…</option>
                {botOptions.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </label>
            {botOptions.length === 0 && (
              <p className="ent-form__hint">
                No voice agents found. An administrator must assign a bot configuration to your account first.
              </p>
            )}
          </div>
        </section>

        <section className="cmp-create__section cmp-create__section--last">
          <h3 className="cmp-create__section-title">
            <span className="cmp-create__section-num">3</span>
            <span>Leads</span>
          </h3>
          <label className="cmp-create__upload">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => update({ file: e.target.files?.[0] || null })}
            />
            <span className="material-symbols-outlined">upload_file</span>
            <div>
              <strong>{form.file ? form.file.name : 'Upload leads CSV'}</strong>
              <p>Optional — you can upload leads after creation.</p>
            </div>
          </label>
        </section>
      </div>
    </Modal>
  );
};

export default CreateCampaignModal;
