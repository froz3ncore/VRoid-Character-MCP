"""Build an explicit garment profile; no character-specific names in the backend."""
import argparse,hashlib,json
from pathlib import Path
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--rig',required=True)
    p.add_argument('--mesh',action='append',required=True);p.add_argument('--reference',action='append',required=True,help='label=path')
    p.add_argument('--height-range',nargs=2,type=float,required=True)
    p.add_argument('--front-axis',choices=['+X','-Y'],default='+X');p.add_argument('--max-displacement',type=float,default=.012)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    source=args.source.resolve();refs=[]
    for spec in args.reference:
        label,path=spec.split('=',1);path=Path(path).resolve()
        refs.append({'label':label,'path':str(path),'sha256':digest(path)})
    coord=[[0,-1,0,0],[0,0,1,0],[1,0,0,0],[0,0,0,1]] if args.front_axis=='+X' else [[-1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]]
    profile={'schema':'vroid-garment-fit-profile-v1','source_blend':str(source),'source_sha256':digest(source),
        'rig':args.rig,'meshes':args.mesh,'coordinate_matrix':coord,'references':refs,
        'source_height_range_m':args.height_range,'limits':{'clearance_m':.004,'inside_threshold_m':.003,
        'max_surface_distance_m':.12,'max_displacement_m':args.max_displacement,'iterations':8}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x',encoding='utf8') as stream:json.dump(profile,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(str(args.out.resolve()))
if __name__=='__main__':main()
