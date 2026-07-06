import './CustomMetadataFields.css';

const CustomMetadataFields = ({ fields, onChange }) => {
  const addField = () => onChange([...fields, { key: '', value: '' }]);

  const updateField = (index, patch) => {
    onChange(fields.map((field, i) => (i === index ? { ...field, ...patch } : field)));
  };

  const removeField = (index) => {
    onChange(fields.filter((_, i) => i !== index));
  };

  return (
    <div className="ent-custom-cols">
      <div className="ent-custom-cols__head">
        <span className="ent-custom-cols__label">Custom columns</span>
        <button type="button" className="ent-custom-cols__add" onClick={addField}>
          <span className="material-symbols-outlined">add</span>
          Add column
        </button>
      </div>
      {fields.length === 0 ? (
        <p className="ent-form__hint">Add extra data fields for this lead (e.g. Project, Budget).</p>
      ) : (
        <div className="ent-custom-cols__list">
          {fields.map((field, index) => (
            <div key={`col-${index}`} className="ent-custom-cols__row">
              <input
                type="text"
                placeholder="Column name"
                value={field.key}
                onChange={(e) => updateField(index, { key: e.target.value })}
              />
              <input
                type="text"
                placeholder="Value"
                value={field.value}
                onChange={(e) => updateField(index, { value: e.target.value })}
              />
              <button
                type="button"
                className="ent-custom-cols__remove"
                onClick={() => removeField(index)}
                aria-label="Remove column"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default CustomMetadataFields;
