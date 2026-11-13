// Behavioral tests: changing the transform/receipt/clone algorithm must fail these.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = '../agent/hair_groups.js';
if (fs.existsSync(require('node:path').join(__dirname, source)))
    vm.runInThisContext(fs.readFileSync(require('node:path').join(__dirname, source), 'utf8'));
assert.equal(typeof globalThis.createHairGroupApi, 'function', 'aggregate hair group API is missing');
const cp = p => ({point:p, normal:[.1,.2,.3], uv:[.4,.5], extra:123});
const original = () => ({scope:'t/g',transferable_id:'t',group_id:'g',owner:{id:'owner',type:'HairGroup',revision:'r1'},category:'HairFront',type:'brush',material:'m',guide:[2,3,4],
    strands:[{id:'t/g/a',type:'brush',material:'a',points:[cp([2,3,4]),cp([4,5,6]),cp([0,1,2])]},
        {id:'t/g/b',type:'brush',material:'b',points:[cp([-3,1,2]),cp([-1,-1,6])]},
        {id:'t/g/c',type:'brush',material:'c',points:[cp([8,8,8])]},
        {id:'t/g/d',type:'brush',material:'d',points:[]}]});
function fixture(options={}) {
    let groups=[options.group||original()], writes=[], cloneCalls=0, invalid=false;
    const adapter={
        begin:()=>({token:'fresh',frame:7}), end(){},
        identity:()=>{if(invalid)throw Error('STALE_MODEL');},
        list:()=>structuredClone(groups),
        snapshot:(_,category,scope)=>structuredClone(groups.find(g=>g.scope===scope)),
        move(_,scope,strand,index,point,onInvoke){
            if(writes.length===options.ownerFailAt)throw Error('HAIR_OWNERSHIP_CHANGED');
            onInvoke?.();
            if(writes.length===options.failAt)throw Error('injected point failure');
            writes.push([scope,strand,index,structuredClone(point)]);
            const s=groups.find(g=>g.scope===scope).strands.find(s=>s.id===strand);
            if(!options.noop)s.points[index]={...structuredClone(point),point:point.point.map(Math.fround)};
            if(options.invalidateAt===writes.length)invalid=true;
        },
        clone(_,category,scope,onInvoke){onInvoke?.();cloneCalls++; for(let i=0;i<(options.added??1);i++){
            const next=structuredClone(groups[0]); next.scope='t/new'+i;
            next.group_id='new'+i;
            if(options.foreignClone){next.scope='other/new'+i;next.transferable_id='other';}
            next.strands.forEach((s,j)=>s.id=next.scope+'/'+j);groups.push(next);
        }if(options.removeSource)groups.shift();},
    };
    return {api:createHairGroupApi({adapter}),groups:()=>groups,writes:()=>writes,clones:()=>cloneCalls};
}
const args={expected_model:'fresh',category:'HairFront',scope:'t/g'};
for(const factor of [.5,2,1]){
    const f=fixture(), before=original(), result=f.api.operations.scale_brush_hair({...args,factor});
    assert.equal(result.ok,true); assert.equal(result.command_count,3);assert.equal(result.affected_strands,factor===1?0:2);
    assert.equal(result.verified_points.length,3);assert.equal(result.affected_points,factor===1?0:3);
    for(let j=0;j<before.strands.length;j++)for(let i=0;i<before.strands[j].points.length;i++){
        const a=before.strands[j].points[i], b=f.groups()[0].strands[j].points[i],root=before.strands[j].points[0].point;
        assert.deepEqual(b.point,a.point.map((v,k)=>root[k]+(v-root[k])*factor));
        assert.deepEqual({...b,point:undefined},{...a,point:undefined});
    }
    assert.equal(f.groups()[0].material,'m');assert.deepEqual(f.groups()[0].guide,[2,3,4]);
}
for(const factor of [0,-1,11,Infinity,NaN,true,'2']){
    const f=fixture(),r=f.api.operations.scale_brush_hair({...args,factor});assert.match(r.error,/FACTOR/);assert.equal(r.uncertain,false);
    assert.equal(f.writes().length,0);assert.equal(f.clones(),0);
}
for(const offset of [[0,1,Infinity],[1,2],['1',2,3],[true,2,3]]){
    const f=fixture(),r=f.api.operations.clone_brush_hair({...args,offset});assert.match(r.error,/OFFSET/);assert.equal(f.clones(),0);
}
{
    const f=fixture();
    const r=f.api.operations.clone_brush_hair({...args,offset:[1e300,0,0]});
    assert.equal(r.dispatch_state,'prewrite_rejected');assert.equal(r.uncertain,false);
    assert.equal(f.clones(),0);assert.equal(f.writes().length,0);
}
{
    const group=original();group.strands[0].points[1].point[0]=3e38;
    const f=fixture({group});
    const r=f.api.operations.scale_brush_hair({...args,factor:10});
    assert.equal(r.dispatch_state,'prewrite_rejected');assert.equal(r.uncertain,false);
    assert.equal(f.writes().length,0);
}
{
    const f=fixture(),r=f.api.operations.clone_brush_hair({...args,offset:[1,-2,3]});
    assert.equal(r.ok,true);assert.equal(r.new_scope,'t/new0');assert.equal(r.command_count,7);
    assert.equal(r.affected_points,6);assert.equal(f.clones(),1);assert.equal(r.new_strand_ids.length,4);
    const before=original();assert.deepEqual(f.groups()[0],before);
    for(let j=0;j<before.strands.length;j++)for(let i=0;i<before.strands[j].points.length;i++){
        const a=before.strands[j].points[i],b=f.groups()[1].strands[j].points[i];
        assert.deepEqual(b.point,a.point.map((v,k)=>v+[1,-2,3][k]));
        assert.deepEqual({...a,point:undefined},{...b,point:undefined});
    }
}
{
    const f=fixture(),r=f.api.operations.clone_brush_hair({...args,offset:[0,0,0]});
    assert.equal(r.ok,true);assert.equal(r.command_count,1);assert.equal(f.writes().length,0);
    assert.equal(r.cloned_strand_count,4);assert.equal(r.cloned_point_count,6);
}
for(const added of [0,2]){
    const f=fixture({added}),r=f.api.operations.clone_brush_hair({...args,offset:[1,2,3]});
    assert.equal(r.ok,false);assert.equal(r.uncertain,true);assert.equal(r.command_count,1);assert.equal(f.writes().length,0);
    assert.equal(r.added_group_ids.length,added);
}
{
    const f=fixture({failAt:2}),r=f.api.operations.scale_brush_hair({...args,factor:2});
    assert.equal(r.ok,false);assert.equal(r.partial,true);assert.equal(r.uncertain,true);
    assert.equal(r.command_count,2);assert.equal(r.attempted_commands,3);assert.equal(r.completed_points.length,2);
}
{
    const f=fixture({failAt:1}),r=f.api.operations.clone_brush_hair({...args,offset:[1,2,3]});
    assert.equal(r.command_count,2);assert.equal(r.attempted_commands,3);assert.equal(r.new_scope,'t/new0');assert.equal(r.partial,true);
}
{
    const f=fixture({invalidateAt:1}),r=f.api.operations.scale_brush_hair({...args,factor:2});
    assert.equal(r.ok,false);assert.equal(f.writes().length,1);assert.equal(r.command_count,1);assert.match(r.error,/STALE_MODEL/);
}
{
    const f=fixture(),r=f.api.operations.list_hair_groups({expected_model:'fresh'});
    assert.equal(r.groups[0].strand_count,4);assert.equal(r.coordinate_space,'native_control_point');
    assert.equal(r.groups[0].control_point_polyline_length, (3*Math.sqrt(12)+Math.sqrt(24))/4);
    assert.equal(r.rendered_strand_length,null);
}
console.log('Hair group behavioral transforms, receipts, clones, bounds and geometry passed');
for(const options of [{foreignClone:true},{removeSource:true}]){
    const f=fixture(options),r=f.api.operations.clone_brush_hair({...args,offset:[1,2,3]});
    assert.equal(r.ok,false);assert.equal(r.uncertain,true);assert.equal(f.writes().length,0);
}
{
    const group=original();group.strands=[{id:'t/g/tiny',type:'brush',points:[cp([0,0,0]),cp([Math.fround(1e-6),0,0])]}];
    const f=fixture({group,noop:true}),r=f.api.operations.scale_brush_hair({...args,factor:2});
    assert.equal(r.ok,false);assert.equal(r.command_count,1);assert.equal(r.affected_points,0);assert.equal(r.verified_points.length,0);
}
for(const [failure,completed,attempted] of [[{ownerFailAt:0},0,0],[{ownerFailAt:1},1,1],[{failAt:0},0,1]]){
    const f=fixture(failure),r=f.api.operations.scale_brush_hair({...args,factor:2});
    assert.equal(r.command_count,completed);assert.equal(r.attempted_commands,attempted);
    assert.equal(r.uncertain,attempted>0);assert.equal(r.dispatch_state,attempted?'invocation_unconfirmed':'prewrite_rejected');
}
{
    const f=fixture(),r=f.api.operations.scale_brush_hair({...args,scope:'missing',factor:2});
    assert.equal(r.ok,false);assert.equal(r.command_count,0);assert.equal(r.uncertain,false);
}
