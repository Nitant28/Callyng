import { TableHeader, TableLoading, TableEmpty, TablePagination } from '../../../components/ui/Table';
import LeadRow from './LeadRow';
import './LeadTable.css';
import '../../../components/ui/Table/table.css';

const COLUMNS = [
  { key: 'check', label: '', width: 44, className: 'ent-table__check' },
  { key: 'lead', label: 'Lead', sortable: true, sortKey: 'name' },
  { key: 'phone', label: 'Phone' },
  { key: 'campaign', label: 'Campaign' },
  { key: 'status', label: 'Status', sortable: true, sortKey: 'status' },
  { key: 'outcome', label: 'Outcome', sortable: true, sortKey: 'outcome' },
  { key: 'attempts', label: 'Attempts', sortable: true, sortKey: 'attempts' },
  { key: 'duration', label: 'Duration' },
  { key: 'lastCall', label: 'Last Call', sortable: true, sortKey: 'updated_at' },
  { key: 'actions', label: '', width: 120 },
];

const LeadTable = ({
  rows,
  loading,
  total,
  page,
  limit,
  sort,
  onSort,
  selected,
  onToggleSelect,
  onToggleSelectAll,
  onRowClick,
  onEdit,
  onDelete,
  onPageChange,
  onLimitChange,
  onImport,
  onAddLead,
}) => {
  const colSpan = COLUMNS.length;

  return (
    <div className="cl-page-container font-inter">
      <div className="ent-table-scroll">
        <table className="ent-table">
          <TableHeader columns={COLUMNS} sort={sort} onSort={onSort} />
          <tbody>
            {loading && <TableLoading colSpan={colSpan} />}
            {!loading && rows.length === 0 && (
              <TableEmpty
                colSpan={colSpan}
                title="No leads yet"
                description="Upload a CSV or add leads manually to get started."
                action={
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                    <button type="button" className="ls-row__action-btn" onClick={onImport}>Upload CSV</button>
                    <button type="button" className="ls-row__action-btn ls-row__action-btn--primary" onClick={onAddLead}>Add Lead</button>
                  </div>
                }
              />
            )}
            {!loading && rows.map((lead) => (
              <LeadRow
                key={lead.id}
                lead={lead}
                selected={selected.has(lead.id)}
                onToggleSelect={onToggleSelect}
                onClick={onRowClick}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </tbody>
        </table>
      </div>
      <TablePagination
        page={page}
        limit={limit}
        total={total}
        onPageChange={onPageChange}
        onLimitChange={onLimitChange}
        limitOptions={[10, 25, 50, 100]}
      />
    </div>
  );
};

export default LeadTable;
