const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('agent/capture_framing.js','utf8'));
const box={min:[-.8,0,-.2],max:[.8,1.7,.25]},near=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} != ${b}`);
for(const region of ['body','face','head','upper','legs','feet']){
    for(const angle of ['front','back','left','right','three_quarter_left','three_quarter_right']){
        const parsed=parseCaptureView(`${region}_${angle}`,true),p=regionalCameraPlan(box,parsed);
        assert.equal(p.region,region);assert.ok(p.distance>0);
        const translated=regionalCameraPlan({min:box.min.map(x=>x+7),max:box.max.map(x=>x+7)},parsed);
        translated.position.forEach((x,i)=>near(x,p.position[i]+7));
        const scaled=regionalCameraPlan({min:box.min.map(x=>x*2),max:box.max.map(x=>x*2)},parsed);
        scaled.position.forEach((x,i)=>near(x,p.position[i]*2));
    }
    for(const [left,right] of [['left','right'],['three_quarter_left','three_quarter_right']]){
        const a=regionalCameraPlan(box,parseCaptureView(`${region}_${left}`)),b=regionalCameraPlan(box,parseCaptureView(`${region}_${right}`));
        near(a.distance,b.distance);assert.deepEqual(a.target,b.target);
        near(a.position[0]-a.target[0],b.target[0]-b.position[0]);near(a.position[2],b.position[2]);
    }
}
// All eight body-box corners must fit the perspective camera for every angle.
for(const angle of ['front','back','left','right','three_quarter_left','three_quarter_right']){
    const p=regionalCameraPlan(box,parseCaptureView(`body_${angle}`));
    const dx=(p.position[0]-p.target[0])/p.distance,dz=(p.position[2]-p.target[2])/p.distance;
    for(const x of [box.min[0],box.max[0]])for(const y of [box.min[1],box.max[1]])for(const z of [box.min[2],box.max[2]]){
        const relative=[x-p.target[0],y-p.target[1],z-p.target[2]],depth=p.distance-relative[0]*dx-relative[2]*dz;
        assert.ok(Math.abs(relative[0]*dz-relative[2]*dx)<depth*Math.tan(Math.PI/12));
        assert.ok(Math.abs(relative[1])<depth*Math.tan(Math.PI/12));
    }
}
for(const name of ['face:left','FACE_left','face','feet_diagonal','../front','face_left.png'])assert.throws(()=>parseCaptureView(name));
for(const b of [null,{min:[0,0,0],max:[1,1,NaN]},{min:[0,0,0],max:[1,.01,1]},{min:[0,0,0],max:[0,1,1]}])assert.throws(()=>regionalCameraPlan(b,parseCaptureView('face_left')));
assert.equal(parseCaptureView('side').regional,false);assert.throws(()=>parseCaptureView('full_front',true));
console.log('36 views, mirror equality, scaling/translation, body projection and invalid inputs passed');
