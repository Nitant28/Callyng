import './table.css';

const SortIcon = ({ active, direction }) => (
  <span className="ent-table__sort" aria-hidden>
    <span style={{ opacity: active && direction === 'asc' ? 1 : 0.4 }}>▲</span>
    <span style={{ opacity: active && direction === 'desc' ? 1 : 0.4 }}>▼</span>
  </span>
);

export const TableHeader = ({ columns, sort, onSort }) => (
  <thead>
    <tr>
      {columns.map((col) => {
        const sortable = col.sortable && col.sortKey;
        const active = sortable && sort?.field === col.sortKey;
        return (
          <th
            key={col.key}
            className={[
              col.className,
              sortable ? 'ent-table__header--sortable' : '',
              active ? 'ent-table__header--active' : '',
            ].filter(Boolean).join(' ')}
            style={col.width ? { width: col.width } : undefined}
            onClick={sortable ? () => onSort?.(col.sortKey) : undefined}
            aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
          >
            {col.label}
            {sortable && <SortIcon active={active} direction={sort?.direction} />}
          </th>
        );
      })}
    </tr>
  </thead>
);

export const TableLoading = ({ colSpan = 6, rows = 6 }) => (
  <>
    {Array.from({ length: rows }).map((_, i) => (
      <tr key={i} className="ent-table__skel-row">
        <td colSpan={colSpan}>
          <div className="ent-table__skel-bar" style={{ width: `${55 + (i % 3) * 12}%` }} />
        </td>
      </tr>
    ))}
  </>
);

export const TableEmpty = ({ colSpan, icon = 'person_off', title, description, action }) => (
  <tr>
    <td colSpan={colSpan} className="ent-table__empty">
      {icon && <span className="material-symbols-outlined" style={{ fontSize: 40, color: 'var(--text-subtle)', marginBottom: 8 }}>{icon}</span>}
      <p style={{ fontWeight: 600, fontSize: 16, color: 'var(--text)', margin: '0 0 4px' }}>{title}</p>
      {description && <p style={{ fontSize: 14, color: 'var(--text-muted)', margin: '0 0 12px' }}>{description}</p>}
      {action}
    </td>
  </tr>
);

export const TablePagination = ({
  page,
  limit,
  total,
  onPageChange,
  onLimitChange,
  limitOptions = [25, 50, 100],
}) => {
  const pages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <footer className="ent-table-pagination">
      <span className="ent-table-pagination__info">
        Showing <strong>{start.toLocaleString('en-IN')}</strong>–<strong>{end.toLocaleString('en-IN')}</strong> of{' '}
        <strong>{total.toLocaleString('en-IN')}</strong>
      </span>
      <div className="ent-table-pagination__controls">
        <label className="ent-table-pagination__info">
          Rows
          <select
            className="ent-table-pagination__select"
            value={limit}
            onChange={(e) => onLimitChange?.(Number(e.target.value))}
            style={{ marginLeft: 8 }}
          >
            {limitOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <div className="ent-table-pagination__pages">
          <button
            type="button"
            className="ent-table-pagination__btn"
            disabled={page <= 1}
            onClick={() => onPageChange?.(page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="ent-table-pagination__btn"
            disabled={page >= pages}
            onClick={() => onPageChange?.(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </footer>
  );
};

const Table = ({ children, className = '' }) => (
  <div className={`ent-table-wrap ${className}`}>
    <div className="ent-table-scroll">
      <table className="ent-table">{children}</table>
    </div>
  </div>
);

export default Table;
