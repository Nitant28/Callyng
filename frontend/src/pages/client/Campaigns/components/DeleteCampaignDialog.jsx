import { Button, Modal } from '../../../../components/enterprise';

const DeleteCampaignDialog = ({ open, campaign, onClose, onConfirm, loading }) => (
  <Modal
    open={open}
    onClose={onClose}
    title="Cancel campaign?"
    width={440}
    footer={(
      <>
        <Button variant="ghost" onClick={onClose}>Keep</Button>
        <Button variant="danger" loading={loading} onClick={onConfirm}>
          Cancel campaign
        </Button>
      </>
    )}
  >
    <p style={{ fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.5 }}>
      This will stop <strong>{campaign?.name}</strong> and mark it as cancelled.
      In-flight calls may still complete before the campaign fully stops.
    </p>
  </Modal>
);

export default DeleteCampaignDialog;
