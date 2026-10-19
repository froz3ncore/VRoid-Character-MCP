"""Summaries of measured native transforms; no inference of collision freedom."""
import math

def summarize_motion(samples):
    if len(samples)<3:raise ValueError('At least three native samples are required')
    first=samples[0];reference={b['id']:b for b in first['bones']}
    if not reference:raise ValueError('Native preview has no tracked bones')
    if len(reference)!=len(first['bones']):raise ValueError('Duplicate motion bone identity')
    max_displacement=0.;max_spring_angle=0.
    frames=[s['frame'] for s in samples]
    renderers={(r['id'],r['name'],r['vertices']) for r in first['renderers']}
    for sample in samples:
        if sample['wear_token']!=first['wear_token'] or sample['preview_root']!=first['preview_root']:
            raise ValueError('Native preview identity changed during capture')
        if {(r['id'],r['name'],r['vertices']) for r in sample['renderers']}!=renderers:
            raise ValueError('Native preview renderers changed during capture')
        if {b['id'] for b in sample['bones']}!=set(reference):raise ValueError('Native preview skeleton changed during capture')
        for bone in sample['bones']:
            p,q=bone['position'],bone['local_rotation']
            if len(p)!=3 or len(q)!=4 or not all(math.isfinite(x) for x in p+q):raise ValueError('Non-finite native motion')
            qlen=math.sqrt(sum(x*x for x in q))
            if abs(qlen-1)>.01:raise ValueError('Invalid native rotation')
            before=reference[bone['id']]
            max_displacement=max(max_displacement,math.dist(p,before['position']))
            if bone['name'].startswith(('WM_Skirt_','WM_BackRibbon_')):
                old=before['local_rotation'];oldlen=math.sqrt(sum(x*x for x in old))
                dot=abs(sum(a*b for a,b in zip(q,old))/(qlen*oldlen))
                max_spring_angle=max(max_spring_angle,math.degrees(2*math.acos(min(1.,dot))))
    return {'samples':len(samples),'frames_advanced':all(b>a for a,b in zip(frames,frames[1:])),
        'native_bone_motion_observed':max_displacement>.0001,'max_world_displacement_m':max_displacement,
        'tracked_spring_bones':sum(b['name'].startswith(('WM_Skirt_','WM_BackRibbon_')) for b in first['bones']),
        'max_spring_local_rotation_change_degrees':max_spring_angle,
        'spring_local_rotation_changed':max_spring_angle>.01,'finite_transforms':True,
        'scope':'Sampled native built-in preview; local rotation change does not establish collision freedom or all-animation correctness'}
