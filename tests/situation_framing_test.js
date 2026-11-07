const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_framing.js','utf8'));
assert.equal(typeof situationCameraPlan,'function','situation framing must consume the category profile');
const bounds={min:[2,1,-8],max:[4,3,-4]};
const profile={top:.2,bottom:.8,half:.1,distance:.1,yaw:90,fit:'full-body'};
const p=situationCameraPlan(bounds,profile,.5);
assert.deepEqual(p.target,[3,2,-6]);
assert.deepEqual(p.inactive_fields,['top','bottom','half']);
assert.equal(p.requested_distance_multiplier,.1);
assert(p.distance>=15.9282032302);
assert(p.effective_distance_multiplier>p.requested_distance_multiplier);
// Independent perspective projection of all eight world corners.
for(const x of [2,4])for(const y of [1,3])for(const z of [-8,-4]){
    const depth=p.position[0]-x;
    assert(depth>p.near_clip && depth<p.far_clip);
    assert(Math.abs(z+6)/(depth*Math.tan(Math.PI/12)*.5)<=1);
    assert(Math.abs(y-2)/(depth*Math.tan(Math.PI/12))<=1);
}
const narrow=situationCameraPlan(bounds,{...profile,fit:'region',top:.2,bottom:.3,half:.2},.5);
const wide=situationCameraPlan(bounds,{...profile,fit:'region',top:.2,bottom:.3,half:.7},.5);
assert(wide.distance>narrow.distance);
assert.deepEqual(narrow.target,[3,2.5,-6]);
assert.equal(narrow.region_world_top,2.6);assert.equal(narrow.region_world_bottom,2.4);
const shifted=situationCameraPlan({min:[12,11,2],max:[14,13,6]},profile,.5);
p.position.forEach((v,i)=>assert(Math.abs(shifted.position[i]-v-10)<1e-8));
for(const aspect of [.5,2]){
    const a=situationCameraPlan(bounds,{...profile,fit:'region',half:.7},aspect);
    assert.equal(a.aspect,aspect);assert.equal(a.fov_degrees,30);
    // A world square at the target plane must occupy equal pixel widths/heights
    // for a 512-high output, independently using actual planned eye/target.
    const z=Math.hypot(...a.position.map((v,i)=>v-a.target[i])),h=512,w=h*aspect;
    const squareWidthPixels=.1/(z*Math.tan(a.fov_degrees*Math.PI/360)*a.aspect)*w/2;
    const squareHeightPixels=.1/(z*Math.tan(a.fov_degrees*Math.PI/360))*h/2;
    assert(Math.abs(squareWidthPixels-squareHeightPixels)<1e-8);
}
assert.throws(()=>situationCameraPlan(bounds,{...profile,half:0},1));
console.log('situation translated bounds, yaw, half, aspect, independent full-body corner containment passed');
