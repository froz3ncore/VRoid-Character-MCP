const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/shoe_templates.js','utf8'));
const shoe={id:'a'.repeat(40)+'.transferablegroup',resourceName:'pixiv/VRoid/Clothing/Shoes/N00/001/Shoes.transferablegroup',
    transferableGroupType:'TransferableGroupType.N00.Level1.Shoes'};
const other={...shoe,id:'b'.repeat(40)+'.transferablegroup',transferableGroupType:'TransferableGroupType.N00.Level1.Tops'};
const custom={...shoe,id:'c'.repeat(40)+'.transferablegroup',resourceName:'user/custom-shoe'};
assert.deepEqual(shoeTemplatesFromCatalog({transferableGroups:[other,shoe,custom]}),[{id:shoe.id,label:shoe.resourceName}]);
assert.throws(()=>shoeTemplatesFromCatalog({}),/SHOE_CATALOG_INVALID/);
assert.throws(()=>shoeTemplatesFromCatalog({transferableGroups:[other,custom]}),/SHOE_CATEGORY_UNAVAILABLE/);
assert.throws(()=>shoeTemplatesFromCatalog({transferableGroups:[shoe,shoe]}),/SHOE_CATALOG_AMBIGUOUS/);
assert.throws(()=>shoeTemplatesFromCatalog({transferableGroups:[{...shoe,id:'foreign'}]}),/SHOE_CATALOG_INVALID_ID/);
console.log('Native catalog shoe filtering, custom-item exclusion and ambiguous-ID refusal passed');
