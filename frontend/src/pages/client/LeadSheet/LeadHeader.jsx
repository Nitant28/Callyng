import PageHeader from '../../../components/ui/PageHeader';
import AgentControlButton from '../../../components/agent/AgentControlButton';

const LeadHeader = ({
  agentActive,
  isPausing,
  isRunning,
  agentLoading,
  canStart,
  onAgentToggle,
  runningCampaignName,
}) => (
  <PageHeader
    eyebrow="Leads"
    title="Lead Sheet"
    subtitle={
      agentActive && runningCampaignName
        ? `Agent active on ${runningCampaignName} — live calls pinned to top.`
        : 'Manage all uploaded leads.'
    }
  >
    <AgentControlButton
      agentActive={agentActive}
      isPausing={isPausing}
      isRunning={isRunning}
      loading={agentLoading}
      canStart={canStart}
      onClick={onAgentToggle}
    />
  </PageHeader>
);

export default LeadHeader;
