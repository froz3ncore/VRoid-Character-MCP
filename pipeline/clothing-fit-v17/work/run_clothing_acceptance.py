import runpy,sys
from pathlib import Path
ROOT=Path('D:/vroidmcp');sys.path.insert(0,str(ROOT/'tools'))
import clean_native_clothing as native
native.PROJECT=ROOT/'work/clothing-mcp-v17b'
native.LAB=ROOT/'lab-clothing-fit-v17'
assert (native.PROJECT/'SOURCE_ISOLATION.json').is_file()
sys.argv=[str(ROOT/'tools/accept_refined_native_wear.py')]+sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
