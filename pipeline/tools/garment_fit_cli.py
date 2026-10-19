"""Run the same Blender MCP fitting backend in an independent background process."""
import argparse,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vroid_mcp_garment_fit',ROOT/'blender-addons/vroid_xwear_direct/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
args=sys.argv[sys.argv.index('--')+1:]
p=argparse.ArgumentParser();p.add_argument('task',choices=['inspect','analyze','plan','apply'])
p.add_argument('--profile');p.add_argument('--plan');p.add_argument('--out');a=p.parse_args(args)
if a.task=='inspect':result=fit.inspect_binding(a.profile)
elif a.task=='apply':result=fit.apply_fit(a.plan,a.out)
else:result=fit.plan_fit(a.profile,a.out,solve=a.task=='plan')
print('GARMENT_FIT_RESULT '+json.dumps(result,ensure_ascii=False),flush=True)
