const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/groups.js','utf8'));
const root={id:'root',type:'Tops',resource_name:'resource',revision:'new'};
for(const node of [
    {...root,revision:'old',updated_since_last_revision:false,entries:[]},
    {...root,revision:null,updated_since_last_revision:false,entries:[]},
    {...root,updated_since_last_revision:true,entries:[]},
    {...root,entries:[]},
])assert.throws(()=>certifySituationMembers(root,[root],()=>node),'stored revision/clean version must independently agree');
const child={id:'child',type:'Hat',resource_name:'child-resource',revision:'new'};
assert.throws(()=>certifySituationMembers(root,[root,child],id=>id==='root'?{
    ...root,updated_since_last_revision:false,entries:[{type:'TransferableGroup',id:'child'}]
}:{...child,revision:'old',updated_since_last_revision:false,entries:[]}));
console.log('stored root revision, missing revision and dirty header refusal passed');
