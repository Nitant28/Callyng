import { normalizeColumnKey } from './leadFieldConfig';

export { normalizeColumnKey };

export const buildMetadataFromCustomFields = (baseMetadata = {}, customFields = []) => {
  const metadata = { ...baseMetadata };
  customFields.forEach(({ key, value }) => {
    const k = normalizeColumnKey(key);
    if (k) metadata[k] = value;
  });
  return metadata;
};
