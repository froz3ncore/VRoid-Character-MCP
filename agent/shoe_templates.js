// 2.16 removed ClothingEditor.ResetTemplates. Its native asset catalog still
// publishes the same built-in shoe group IDs; do not replace them with the ten
// Initial_* entries offered by the separate texture-template dialog.
function shoeTemplatesFromCatalog(catalog) {
    if (!catalog || !Array.isArray(catalog.transferableGroups)) throw Error('SHOE_CATALOG_INVALID');
    const seen = new Set(), rows = [];
    for (const entry of catalog.transferableGroups) {
        if (entry.transferableGroupType !== 'TransferableGroupType.N00.Level1.Shoes'
            || typeof entry.resourceName !== 'string'
            || !entry.resourceName.startsWith('pixiv/VRoid/Clothing/Shoes/N00/')) continue;
        if (typeof entry.id !== 'string' || !/^[a-f0-9]{40}\.transferablegroup$/.test(entry.id))
            throw Error('SHOE_CATALOG_INVALID_ID');
        if (seen.has(entry.id)) throw Error('SHOE_CATALOG_AMBIGUOUS');
        seen.add(entry.id);
        rows.push({id: entry.id, label: entry.resourceName});
    }
    if (!rows.length) throw Error('SHOE_CATEGORY_UNAVAILABLE');
    return rows;
}
