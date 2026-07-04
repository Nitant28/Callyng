import { Button } from '../../../../components/enterprise';
import PageHeader from '../../../../components/ui/PageHeader';

const CampaignHeader = ({ onRefresh, onExport, onCreate, refreshing }) => (
  <PageHeader eyebrow="Campaigns" title="Campaigns" subtitle="How are your campaigns performing?" bordered>
    <Button variant="secondary" icon="refresh" onClick={onRefresh} loading={refreshing}>
      Refresh
    </Button>
    {/* Export/creation removed from client UI per design */}
  </PageHeader>
);

export default CampaignHeader;
