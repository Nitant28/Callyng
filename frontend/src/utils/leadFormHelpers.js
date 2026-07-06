export const normalizeColumnKey = (key) =>
  key.trim().replace(/\s+/g, '_').toLowerCase();

export const buildMetadataFromCustomFields = (baseMetadata = {}, customFields = []) => {
  const metadata = { ...baseMetadata };
  customFields.forEach(({ key, value }) => {
    const k = normalizeColumnKey(key);
    if (k) metadata[k] = value;
  });
  return metadata;
};
