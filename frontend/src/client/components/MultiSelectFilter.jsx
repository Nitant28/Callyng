import React, { useEffect, useRef, useState } from 'react';

/**
 * Compact multi-select for table column filters.
 * Empty selection = "All" (no restriction).
 */
export default function MultiSelectFilter({
  label,
  ariaLabel,
  options,
  value = [],
  onChange,
  className = '',
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = Array.isArray(value) ? value : [];

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const toggle = (optValue) => {
    if (selected.includes(optValue)) {
      onChange(selected.filter((v) => v !== optValue));
    } else {
      onChange([...selected, optValue]);
    }
  };

  const summary = selected.length === 0
    ? 'All'
    : selected.length === 1
      ? (options.find((o) => o.value === selected[0])?.label || selected[0])
      : `${selected.length} selected`;

  return (
    <div className={`cl-th-filter ${className}`} ref={rootRef}>
      <span>{label}</span>
      <div className="cl-multi-filter">
        <button
          type="button"
          className="cl-th-filter__select cl-multi-filter__btn"
          aria-label={ariaLabel || `Filter by ${label}`}
          aria-expanded={open}
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
          }}
        >
          {summary}
        </button>
        {open && (
          <div
            className="cl-multi-filter__menu"
            role="listbox"
            aria-multiselectable="true"
            onClick={(e) => e.stopPropagation()}
          >
            <label className="cl-multi-filter__option">
              <input
                type="checkbox"
                checked={selected.length === 0}
                onChange={() => onChange([])}
              />
              All
            </label>
            {options.map((opt) => (
              <label key={opt.value} className="cl-multi-filter__option">
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={() => toggle(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function joinFilterParam(values) {
  if (!Array.isArray(values) || values.length === 0) return undefined;
  return values.join(',');
}
