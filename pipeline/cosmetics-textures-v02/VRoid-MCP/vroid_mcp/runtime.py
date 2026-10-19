from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import pathlib
import re
import time
import uuid
from typing import Any

import frida
from .supported_builds import validate_assembly
from .preset_labels import name_catalog, name_preset
from .preset_previews import validate_request, decode_thumbnail
from .capture_quality import quality_plan, decode_capture
from .color_state import attach_color_readback
from .parameter_labels import name_parameters

from .capture_views import CAPTURE_VIEWS, is_regional, validate_wear_views, review_reference

PROJECT = pathlib.Path(__file__).resolve().parents[1]


def validate_capture(views: list[str], size: int) -> None:
    if not views or len(views)>6 or len(set(views))!=len(views) or any(v not in CAPTURE_VIEWS for v in views):
        raise ValueError('Choose 1-6 distinct supported views')
    if type(size) is not int or not 256<=size<=2048:
        raise ValueError('Capture size must be an integer from 256 to 2048')


def review_folder(lab: pathlib.Path, capture_id: str) -> pathlib.Path:
    if not re.fullmatch('[0-9a-f]{32}', capture_id):
        raise ValueError('Use a capture_id returned by capture_review')
    folder=lab.resolve()/'reviews'/capture_id
    if folder.resolve()!=folder:
        raise ValueError('Review directories must not be links or junctions')
    return folder


def save_destination(lab: pathlib.Path, filename: str) -> pathlib.Path:
    """A single filename in saves/, never an absolute path or alternate stream."""
    if not filename or any(ord(c)<32 or c in '\\/:<>"|?*' for c in filename) or filename.rstrip(' .') != filename:
        raise ValueError('Use a plain .vroid filename without path separators')
    if not filename.lower().endswith('.vroid') or filename in ('.vroid', '..vroid'):
        raise ValueError('A nonempty .vroid filename is required')
    if filename.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Reserved Windows filename')
    folder = lab.resolve() / 'saves'
    folder.mkdir(exist_ok=True)
    if folder.resolve() != folder:
        raise ValueError('The saves directory must not be a link or junction')
    destination = folder / filename
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Refusing to overwrite an existing file: ' + filename)
    return destination


class Runtime:
    """One Frida owner per lab. It only spawns and owns the designated copy."""
    def __init__(self, lab: pathlib.Path, bridge_js: pathlib.Path | None = None):
        self.lab = lab.resolve()
        self.exe = self.lab / 'app' / 'VRoidStudio.exe'
        self.bridge_js = bridge_js or PROJECT / 'node_modules/frida-il2cpp-bridge/dist/index.js'
        self.pid: int | None = None
        self.device = self.session = self.script = None
        self.lock = asyncio.Lock()
        self.file_lock = None
        self.dead = False
        self.uncertain = False
        self.events: list[dict] = []
        self.run_dir = self.lab / 'runs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])

    def _event(self, data: dict) -> None:
        record = {'time': time.time(), **data}
        self.events.append(record)
        with (self.run_dir/'bridge.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _detached(self, reason, *unused) -> None:
        self.dead = True
        self._event({'event':'detached','reason':reason})

    def start(self) -> None:
        if os.name != 'nt':
            raise RuntimeError('This prototype is validated only on Windows')
        import msvcrt
        if not self.exe.is_file() or not self.bridge_js.is_file():
            raise FileNotFoundError('VRoid copy or frida-il2cpp-bridge is missing')
        # Reject a junction/symlink that could redirect app/ to the original install.
        if self.exe.resolve() != self.exe or (self.lab/'app').resolve() != self.lab/'app':
            raise ValueError('app/ must be a physical copy, not a link')
        validate_assembly(self.lab/'app/GameAssembly.dll')
        self.file_lock=(self.lab/'.mcp-owner.lock').open('a+b')
        self.file_lock.seek(0);self.file_lock.write(b'0');self.file_lock.flush();self.file_lock.seek(0)
        try:msvcrt.locking(self.file_lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file_lock.close();self.file_lock=None
            raise RuntimeError('Another MCP process already owns this lab')
        self.run_dir.mkdir(parents=True)
        for rel in ['Documents','AppData/Local','AppData/LocalLow/pixiv/VRoid Studio/custom_items',
                    'AppData/LocalLow/pixiv/VRoid Studio/XWear/Closet','AppData/Roaming','Temp']:
            (self.lab/'profile'/rel).mkdir(parents=True,exist_ok=True)
        env=dict(os.environ)
        env.update(USERPROFILE=str(self.lab/'profile'),APPDATA=str(self.lab/'profile/AppData/Roaming'),
                   LOCALAPPDATA=str(self.lab/'profile/AppData/Local'),TEMP=str(self.lab/'profile/Temp'),TMP=str(self.lab/'profile/Temp'))
        config={'root':str(self.lab),'exe':str(self.exe),'originalProfile':os.environ['USERPROFILE'],'excludedPids':[],
                'registryKey':'Software\\VRoidFaceMCP\\'+hashlib.sha256(str(self.lab).lower().encode()).hexdigest()[:16]}
        self.device=frida.get_local_device()
        try:
            argv=[str(self.exe),'-logFile',str(self.run_dir/'Player.log'),
                '-screen-fullscreen','0','-screen-width','960','-screen-height','720']
            self.pid=self.device.spawn(argv,cwd=str(self.exe.parent),env=env,stdio='pipe')
            self.session=self.device.attach(self.pid)
            self.session.on('detached',self._detached)
            parts=['const PROBE='+json.dumps(config)+';',
                   (PROJECT/'agent/isolate.js').read_text(encoding='utf-8'),
                   self.bridge_js.read_text(encoding='utf-8'),
                   (PROJECT/'agent/bootstrap.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/parameter_semantics.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/color_state.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/capture_quality.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/capture_framing.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/parameters.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/textures.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/wear.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/body_reference.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/preset_previews.js').read_text(encoding='utf-8'),
                   (PROJECT/'agent/operations.js').read_text(encoding='utf-8')]
            self.script=self.session.create_script('\n'.join(parts))
            self.script.on('message',lambda message,data:self._event({'event':'agent','message':message}))
            self.script.load();self.device.resume(self.pid)
            self._event({'event':'spawned-copy','pid':self.pid,'exe':str(self.exe)})
        except BaseException:
            self.close();raise

    async def _call(self, operation: str, args: dict | None = None) -> Any:
        if self.dead or self.script is None:
            raise RuntimeError('COPY_DISCONNECTED: restart the MCP server')
        if self.uncertain and operation != 'status':
            raise RuntimeError('PREVIOUS_CALL_UNCERTAIN: restart; do not retry a mutation')
        try:
            # Dense geometry capture is read-only and can serialize tens of MB.
            # Keep the mutation timeout unchanged; allow this bounded snapshot more time.
            timeout=120 if operation=='capture_wear_reference' else 30
            return await asyncio.wait_for(asyncio.to_thread(self.script.exports_sync.call,operation,args or {}),timeout)
        except asyncio.TimeoutError:
            self.uncertain=True
            raise RuntimeError('Native call timed out; result is uncertain and further calls are blocked')

    async def initialize(self, variant: str = 'F00', model_file: pathlib.Path | None = None) -> dict:
        async with self.lock:
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                health=await asyncio.to_thread(self.script.exports_sync.health)
                if health['error']:raise RuntimeError(health['error'])
                if health['ready']:
                    status=await self._call('status')
                    if not status.get('reason','').startswith('Error: NOT_READY'):break
                await asyncio.sleep(.2)
            else:raise TimeoutError('VRoid initialization timed out')
            if model_file is None:
                await self._call('new_model',{'variant':variant})
            else:
                path=model_file.resolve()
                if not path.is_relative_to(self.lab) or path.suffix.lower()!='.vroid' or not path.is_file():
                    raise ValueError('Startup models must be .vroid files already inside the lab')
                await self._task(await self._call('open_model',{'path':str(path)}))
            return await self._settle()

    async def _task(self, task: dict) -> None:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            result=await self._call('task_status',task)
            if result['completed']:
                if result['faulted'] or result['canceled']:raise RuntimeError(result.get('error','Operation canceled'))
                return
            await asyncio.sleep(.1)
        self.uncertain=True
        raise TimeoutError('Managed task did not complete; restart before further changes')

    async def _settle(self, after_frame: int = -1) -> dict:
        deadline=time.monotonic()+30
        quiet=0
        while time.monotonic()<deadline:
            result=await self._call('status')
            if result['model_ready'] and not result['updating'] and not result.get('photo_updating',False) and not result.get('command_busy',False) and (result.get('photo_active',False) or not result.get('presets_loading',False)) and result['frame']>=after_frame+2:
                quiet+=1
                if quiet>=2:return result
            else:quiet=0
            await asyncio.sleep(.1)
        self.uncertain=True
        raise TimeoutError('Model did not finish updating: '+json.dumps(result))

    async def status(self) -> dict:
        async with self.lock:
            if self.dead:
                return {'model_ready':False,'connected':False,'writes_blocked':True,
                        'reason':'COPY_DISCONNECTED','recovery':'restart_session requires discard_unsaved=true'}
            try:
                status=await self._call('status')
            except frida.InvalidOperationError as error:
                if 'script has been destroyed' not in str(error):
                    raise
                self.dead=True
                return {'model_ready':False,'connected':False,'writes_blocked':True,
                        'reason':'COPY_DISCONNECTED','recovery':'restart_session requires discard_unsaved=true'}
            status.update(connected=True,writes_blocked=self.uncertain)
            return status

    async def capture_body_reference(self, expected_model: str, label: str = '') -> dict:
        from .body_reference import validate_body_reference
        from .wear_paths import wear_destination
        if not expected_model:raise ValueError('expected_model is required')
        destination=wear_destination(self.lab,'body-reference-'+uuid.uuid4().hex+'.json','.json')
        async with self.lock:
            wear=await self._call('get_wear_status')
            if wear['active']:raise ValueError('DRESS_UP_ACTIVE: body references require ordinary editing and do not capture assemblies')
            await self._settle()
            data=await self._call('capture_body_reference',{'expected_model':expected_model})
            summary=validate_body_reference(data,expected_model)
            data['label']=label
            encoded=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            # Exclusive creation: never overwrite another reference or follow a linked leaf.
            with destination.open('xb') as output:output.write(encoded)
            return {**summary,'captured':True,'path':str(destination),'bytes':len(encoded),
                    'sha256':hashlib.sha256(encoded).hexdigest(),'label':label,'scope':data['scope']}

    async def list_face_params(self) -> dict:
        return await self.list_params('face')

    async def list_params(self, area: str) -> dict:
        if area not in ('face','body','clothing'):raise ValueError('Unsupported parameter area')
        async with self.lock:return name_parameters(await self._call('list_'+area+'_params'))

    async def set_face_params(self, expected_model: str, changes: list[dict]) -> dict:
        return await self.set_params('face',expected_model,changes)

    async def set_params(self, area: str, expected_model: str, changes: list[dict]) -> dict:
        if area not in ('face','body','clothing'):raise ValueError('Unsupported parameter area')
        async with self.lock:
            result=await self._call('set_'+area+'_params',{'expected_model':expected_model,'changes':changes})
            settled=await self._settle(result['frame'])
            if settled['model_token']!=expected_model:raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
            result['settled']=True
            return result

    async def list_presets(self,area: str,category: str|None=None,offset:int=0,limit:int=100) -> dict:
        if area not in ('face','body','hair','clothing'):raise ValueError('Unsupported preset area')
        async with self.lock:
            return name_catalog(await self._call('list_presets',{'area':area,'category':category,'offset':offset,'limit':limit,'owned_only':True}))

    async def preview_presets(self, expected_model: str, area: str, preset_ids: list[str]) -> tuple[dict, list[tuple[str, bytes]]]:
        validate_request(expected_model, area, preset_ids)
        async with self.lock:
            await self._settle()
            # Validate the whole batch against one fresh catalog before preparing resources.
            catalog=await self._call('list_presets',{'expected_model':expected_model,'area':area,'offset':0,'limit':200,'owned_only':True})
            if catalog['model_token']!=expected_model:raise ValueError('Preset catalog identity mismatch')
            options={p['id']:p for p in catalog['presets']}
            while catalog.get('next_offset') is not None and not all(p in options for p in preset_ids):
                catalog=await self._call('list_presets',{'expected_model':expected_model,'area':area,'offset':catalog['next_offset'],'limit':200,'owned_only':True})
                if catalog['model_token']!=expected_model:raise ValueError('Preset catalog identity mismatch')
                options.update((p['id'],p) for p in catalog['presets'])
            if any(p not in options for p in preset_ids):raise ValueError('UNKNOWN_PRESET: relist owned presets')
            items=[];images=[]
            for preset_id in preset_ids:
                args={'expected_model':expected_model,'area':area,'preset_id':preset_id}
                result=await self._call('preset_preview_begin',args)
                request=result.get('request_id')
                try:
                    deadline=time.monotonic()+15
                    while not result.get('completed'):
                        if time.monotonic()>=deadline:raise TimeoutError('Native preset preview did not complete')
                        await asyncio.sleep(.1)
                        result=await self._call('preset_preview_poll',{'expected_model':expected_model,'request_id':request})
                    if result.get('model_token')!=expected_model or result.get('preset_id')!=preset_id:
                        raise ValueError('Native thumbnail identity mismatch')
                    item=name_preset(options[preset_id])
                    if result.get('ok'):
                        metadata,data=decode_thumbnail(result,expected_model,preset_id)
                        item.update(metadata);images.append((preset_id,data))
                    else:item.update({k:v for k,v in result.items() if k!='base64'})
                    items.append(item)
                finally:
                    if request and not self.dead and not self.uncertain:
                        await self._call('preset_preview_cancel',{'expected_model':expected_model,'request_id':request})
            return {'model_token':expected_model,'area':area,'presets':items,
                    'scope':'Native preset thumbnails, not the preset applied to this character'},images

    async def apply_preset(self,area:str,expected_model:str,preset_id:str) -> dict:
        if area not in ('face','body','hair','clothing'):raise ValueError('Unsupported preset area')
        async with self.lock:
            result=await self._call('apply_preset',{'area':area,'expected_model':expected_model,'preset_id':preset_id})
            await self._settle(result['frame'])
            before=result.pop('before_groups',None)
            if result.get('clear'):
                state=await self._call('preset_state',{'area':area,'expected_model':expected_model,'preset_id':preset_id})
                groups=state.get('active_groups',[])
                old_ids={g['id'] for g in before or []};new_ids={g['id'] for g in groups}
                removed=[g for g in before or [] if g['id'] not in new_ids]
                result.update(settled=True,selected=None,changed=groups!=before,
                              active_groups=groups,removed_groups=removed,
                              confirmation='groups_removed' if old_ids-new_ids else 'no_group_removed')
                return result
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                state=await self._call('preset_state',{'area':area,'expected_model':expected_model,'preset_id':preset_id})
                if state['selected']:
                    result.update(settled=True,selected=True);return result
                await asyncio.sleep(.15)
            # Some native hair sets are expanded into parts and no longer retain
            # a selected whole-set checkbox. The native operation has settled;
            # report the evidence without inventing selection or freezing reads.
            groups=state.get('active_groups',[])
            changed=before is not None and groups!=before
            result.update(settled=True,selected=False,changed=changed,
                          confirmation='model_changed_without_preset_checkmark' if changed else 'selection_unconfirmed',
                          active_groups=groups,
                          message='Inspect the model and screenshot; an unchecked set does not establish failure or exact preset equivalence.')
            return result

    async def list_shoe_templates(self,expected_model:str)->dict:
        async with self.lock:
            await self._settle()
            return await self._call('list_shoe_templates',{'expected_model':expected_model})

    async def add_shoe_template(self,expected_model:str,template_id:str)->dict:
        if not isinstance(template_id,str) or not template_id.strip():raise ValueError('A fresh native shoe template ID is required')
        async with self.lock:
            await self._settle()
            result=await self._call('add_shoe_template',{'expected_model':expected_model,'template_id':template_id})
            await self._settle(result['frame'])
            state=await self._call('shoe_template_state',{'expected_model':expected_model})
            if state['model_token']!=expected_model:raise RuntimeError('MODEL_CHANGED_DURING_TEMPLATE_ADD')
            before=result.pop('before_groups');after=state['active_groups']
            old_ids={g['id'] for g in before};new_ids={g['id'] for g in after}
            added=[g for g in after if g['id'] not in old_ids];removed=[g for g in before if g['id'] not in new_ids]
            confirmed=len(added)==1 and added[0]['type'].split('.')[-1]=='Shoes' and not removed
            return {**result,'settled':True,'ok':confirmed,'confirmation':'native_shoe_group_added' if confirmed else 'unconfirmed_model_change',
                    'active_groups':after,'added_groups':added,'removed_groups':removed,'retry_safe':False}

    async def parameter_call(self,operation: str,args:dict|None=None,mutating:bool=False)->dict:
        async with self.lock:
            await self._settle()
            result=await self._call(operation,args or {})
            if operation=='list_parameters':result=name_parameters(result)
            if mutating:
                settled=await self._settle(result.get('frame',-1))
                if settled['model_token']!=(args or {}).get('expected_model'):raise RuntimeError('MODEL_CHANGED_DURING_OPERATION')
                result['settled']=True
                if operation=='set_parameters' and (args or {}).get('domain') in ('colors','accessories'):
                    rows=[];offset=0
                    while True:
                        current=await self._call('list_parameters',{**(args or {}),'offset':offset,'limit':500})
                        if current['model_token']!=(args or {}).get('expected_model'):
                            raise RuntimeError('MODEL_CHANGED_DURING_COLOR_READBACK')
                        rows.extend(name_parameters(current)['parameters'])
                        if current['next_offset'] is None:break
                        offset=current['next_offset']
                    result=attach_color_readback(result,rows)
            return result

    async def set_height(self,expected_model:str,centimeters:float,tolerance_cm:float=.05)->dict:
        import math
        if not math.isfinite(centimeters) or not 20<=centimeters<=400:raise ValueError('Height must be 20..400 cm; native model range can be narrower')
        if not .01<=tolerance_cm<=.5:raise ValueError('Tolerance must be .01...5 cm')
        async with self.lock:
            await self._settle()
            args={'expected_model':expected_model}
            body=await self._call('list_body_params',args)
            p=next(p for p in body['parameters'] if p['id']=='body/WholeBody/002')
            initial=p['value'];x=initial;history=[]
            async def measure():return (await self._call('get_height',args))['centimeters']
            async def change(v):
                result=await self._call('set_body_params',{**args,'changes':[{'id':p['id'],'value':v}]})
                if not result['ok']:raise RuntimeError(result)
                await self._settle(result['frame'])
                return await measure()
            y=await measure()
            for i in range(14):
                history.append({'scale_parameter':x,'centimeters':y})
                if abs(y-centimeters)<=tolerance_cm:
                    return {'model_token':expected_model,'target_cm':centimeters,'measured_cm':y,'error_cm':y-centimeters,
                            'tolerance_cm':tolerance_cm,'scale_parameter':x,'samples':history,'settled':True,
                            'measurement':'VRoid native BodyHeightValue; hairstyle and model proportions can affect this measurement'}
                if len(history)==1:next_x=min(1,x+.05) if x<.95 else x-.05
                else:
                    prev=history[-2];slope=(y-prev['centimeters'])/(x-prev['scale_parameter']) if x!=prev['scale_parameter'] else 0
                    if abs(slope)<1e-6:break
                    next_x=max(p['min'],min(p['max'],x+(centimeters-y)/slope))
                if abs(next_x-x)<1e-7:break
                x=next_x;y=await change(x)
            restored=await change(initial)
            raise ValueError(f'Height did not converge within native range; original scale restored ({restored:.3f} cm)')

    async def history(self, method: str, expected_model: str, steps: int = 1) -> dict:
        if method not in ('undo','redo') or not 1<=steps<=32:raise ValueError('Invalid history operation')
        async with self.lock:
            for _ in range(steps):
                result=await self._call(method,{'expected_model':expected_model})
                await self._task(result);await self._settle(result['frame'])
            return name_parameters(await self._call('list_face_params',{'expected_model':expected_model}))

    async def _capture(self, view: str, expected_model: str, size: int, quality: str = 'balanced', metadata: dict | None = None, framing_metadata: dict | None = None, framing_reference: dict | None = None) -> bytes:
        result=await self._call('screenshot',{'view':view,'expected_model':expected_model,'size':size,'quality':quality,'framing_reference':framing_reference})
        if metadata is not None:metadata.update(result['quality'])
        if framing_metadata is not None and 'framing' in result:framing_metadata.update(result['framing'])
        return decode_capture(result,size,quality)

    async def screenshot(self, view: str, expected_model: str, size: int = 512, quality: str = 'balanced') -> bytes:
        validate_capture([view],size)
        quality_plan(size,quality)
        async with self.lock:
            await self._settle()
            prepared=await self._call('prepare_capture',{'expected_model':expected_model})
            await self._settle(prepared['frame'])
            return await self._capture(view,expected_model,size,quality)

    async def capture_review(self, expected_model: str, views: list[str], size: int = 1024,
                             label: str = '', baseline_id: str | None = None, quality: str = 'balanced') -> tuple[dict,list[tuple[str,bytes]]]:
        """Native views plus numeric evidence; visual quality is assessed by the caller."""
        validate_capture(views,size)
        quality_plan(size,quality)
        if 'photo' in views:
            raise ValueError('Use screenshot for animated photo previews; review uses reproducible model views')
        if len(label)>80:raise ValueError('Label must be at most 80 characters')
        baseline=None;images=[]
        if baseline_id:
            previous=review_folder(self.lab,baseline_id)
            metadata=previous/'review.json'
            if metadata.resolve()!=metadata:raise ValueError('Baseline metadata must not be a link')
            baseline=json.loads(metadata.read_text(encoding='utf8'))
            if baseline['views']!=views or baseline['size']!=size:
                raise ValueError('Baseline views and size must match for a fair comparison')
            if baseline.get('quality','legacy')!=quality:
                raise ValueError('Baseline capture quality must match for a fair comparison')
            for view in views:
                source=previous/(view+'.png')
                if source.resolve()!=source:raise ValueError('Baseline images must not be links')
                data=source.read_bytes()
                if hashlib.sha256(data).hexdigest()!=baseline['images'][view]['sha256']:
                    raise ValueError('Baseline image was modified')
                images.append(('before / '+view,data))
        async with self.lock:
            status=await self._settle()
            if status['model_token']!=expected_model:raise ValueError('MODEL_CHANGED')
            if status.get('photo_active'):raise ValueError('Return to edit mode before capture_review')
            prepared=await self._call('prepare_capture',{'expected_model':expected_model})
            await self._settle(prepared['frame'])
            framing_reference=None;framing_mode=None
            if any(is_regional(v) for v in views):
                fresh=await self._call('capture_framing_reference',{'expected_model':expected_model})
                framing_reference,framing_mode=review_reference(fresh,baseline)
            current=[]
            for view in views:
                metadata={};framing={}
                data=await self._capture(view,expected_model,size,quality,metadata,framing,framing_reference)
                if baseline and baseline['images'][view].get('quality',{}).get('msaa_samples',1)!=metadata['msaa_samples']:
                    raise ValueError('Baseline effective MSAA must match for a fair comparison')
                current.append((view,data,metadata,framing))
            state={}
            for area in ('face','body','clothing'):
                state[area]=await self._call('list_'+area+'_params',{'expected_model':expected_model})
            state['colors']=await self._call('list_parameters',{'domain':'colors','limit':200,'expected_model':expected_model})
            state['height']=await self._call('get_height',{'expected_model':expected_model})
            final=await self._call('status')
            if final['model_token']!=expected_model:raise ValueError('MODEL_CHANGED_DURING_CAPTURE')
        capture_id=uuid.uuid4().hex;folder=review_folder(self.lab,capture_id)
        folder.mkdir(parents=True,exist_ok=False)
        manifest={'capture_id':capture_id,'label':label,'model_token':expected_model,
                  'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'views':views,'size':size,
                  'baseline_id':baseline_id,'quality':quality,'state':state,'images':{},
                  'visual_review_required':True,
                  'checklist':['eye and eyebrow balance','bangs obscuring eyes','hair/scalp gaps',
                               'hair/clothing intersections','head/body and limb proportions','front/side/back silhouette'],
                  'limitations':'Native rendered evidence, not an automated beauty score or geometry collision test. Hair simulation may vary between frames.'}
        if framing_reference:manifest.update(framing_reference=framing_reference,framing_mode=framing_mode)
        for view,data,metadata,framing in current:
            path=folder/(view+'.png');path.write_bytes(data)
            manifest['images'][view]={'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'quality':metadata}
            if framing:manifest['images'][view]['framing']=framing
            images.append(('after / '+view if baseline else view,data))
        if baseline:
            changes=[]
            for area in ('face','body','clothing','colors'):
                old={p['id']:p['value'] for p in baseline['state'][area]['parameters']}
                for p in state[area]['parameters']:
                    if not p.get('alias_of') and old.get(p['id'])!=p['value']:
                        changes.append({'area':area,'id':p['id'],'label':p['label'],'before':old.get(p['id']),'after':p['value']})
            manifest['parameter_changes']=changes
            manifest['baseline_same_model_token']=baseline['model_token']==expected_model
        manifest['manifest_path']=str(folder/'review.json')
        (folder/'review.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        return manifest,images

    async def save_as(self, filename: str, expected_model: str) -> dict:
        async with self.lock:
            destination=save_destination(self.lab,filename)
            staging=destination.parent/('stage-'+uuid.uuid4().hex+'.vroid')
            await self._settle()
            await self._call('save_as',{'path':str(staging),'expected_model':expected_model})
            if not staging.is_file() or staging.stat().st_size<100:
                raise RuntimeError('VRoid did not produce a valid-sized file')
            # On Windows os.rename fails if destination exists; never use os.replace.
            os.rename(staging,destination)
            return {'path':str(destination),'bytes':destination.stat().st_size,'model_token':expected_model,
                    'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

    async def wear_status(self) -> dict:
        async with self.lock:
            return await self._call('get_wear_status')

    async def wear_snapshot(self, expected_wear: str) -> dict:
        async with self.lock:
            return await self._call('get_wear_snapshot',{'expected_wear':expected_wear})

    async def sample_wear_preview_rig(self,expected_wear:str)->dict:
        async with self.lock:
            result=await self._call('sample_wear_preview_rig',{'expected_wear':expected_wear})
            if result['wear_token']!=expected_wear or result['model_modified'] is not False or not result['nodes']:raise ValueError('Native preview rig identity/state changed')
            ids=set()
            if len(result['nodes'])>4096:raise ValueError('Native preview rig node limit')
            for node in result['nodes']:
                if node['id'] in ids:raise ValueError('Duplicate native bone identity')
                ids.add(node['id']);matrix=node['world_matrix']
                if len(matrix)!=4 or any(len(row)!=4 for row in matrix) or any(type(v) not in (int,float) or not math.isfinite(v) for row in matrix for v in row):raise ValueError('Malformed native bone matrix')
                if max(abs(a-b) for a,b in zip(matrix[3],[0,0,0,1]))>1e-5:raise ValueError('Nonaffine native bone matrix')
            return result

    async def wear_preview_clips(self, expected_wear: str) -> dict:
        async with self.lock:
            return await self._call('list_wear_preview_clips',{'expected_wear':expected_wear})

    async def select_wear_preview_clip(self, expected_wear: str, clip_id: str | None) -> dict:
        if clip_id is not None and (not isinstance(clip_id,str) or not re.fullmatch('0x[0-9a-fA-F]+',clip_id)):
            raise ValueError('Use a session-local clip ID from list_wear_preview_clips, or null to restore default')
        async with self.lock:
            return await self._call('select_wear_preview_clip',{'expected_wear':expected_wear,'clip_id':clip_id})

    async def capture_wear_reference(self, expected_wear: str, item_id: str, mesh_names: list[str] | None = None, preview: bool = False, include_base_meshes: bool = False, base_mesh_names: list[str]|None=None) -> dict:
        from .wear_paths import wear_destination
        from .wear_reference import validate_wear_reference
        if type(preview) is not bool:raise ValueError('preview must be boolean')
        if type(include_base_meshes) is not bool:raise ValueError('include_base_meshes must be boolean')
        if base_mesh_names is not None and (not include_base_meshes or not base_mesh_names or len(base_mesh_names)>4 or len(set(base_mesh_names))!=len(base_mesh_names) or 'Body' not in base_mesh_names or any(n not in ('Body','Foot','Face','Hair') for n in base_mesh_names)):
            raise ValueError('Choose Body and optional distinct Foot/Face/Hair base meshes')
        if mesh_names is not None and (not mesh_names or len(mesh_names)>128 or len(set(mesh_names))!=len(mesh_names) or any(not isinstance(n,str) or not n or len(n)>200 for n in mesh_names)):
            raise ValueError('Choose 1-128 distinct names from get_wear_snapshot')
        async with self.lock:
            data=await self._call('capture_wear_reference',{'expected_wear':expected_wear,'item_id':item_id,'mesh_names':mesh_names,'preview':preview,'include_base_meshes':include_base_meshes,'base_mesh_names':base_mesh_names})
            if data['wear_token']!=expected_wear or data['item_id']!=item_id or data['pose_source']!=('native_preview' if preview else 'native_edit'):
                raise ValueError('Native wear reference identity or pose source changed')
            validate_wear_reference(data)
            if include_base_meshes and 'Body' not in {g['name'] for g in data.get('base_meshes',[])}:
                raise ValueError('Native base Body reference missing')
            payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
            destination=wear_destination(self.lab,'wear-reference-'+uuid.uuid4().hex+'.json',suffix='.json')
            with destination.open('xb') as stream:stream.write(payload)
            return {'captured':True,'schema':data['schema'],'wear_token':data['wear_token'],'item_id':item_id,'pose_source':data['pose_source'],'frame':data['frame'],
                'path':str(destination),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),
                'body_vertices':len(data['body']['positions']),'garments':[g['name'] for g in data['garments']],
                'garment_vertices':sum(len(g['positions']) for g in data['garments']),'bones':len(data['bones']),
                'base_meshes':[g['name'] for g in data.get('base_meshes',[])],'base_foot_source':data.get('base_foot_source')}

    async def hold_wear_preview_pose(self,expected_wear: str,clip_id: str,seconds: float) -> dict:
        if not isinstance(clip_id,str) or not re.fullmatch('0x[0-9a-fA-F]+',clip_id):raise ValueError('Use a freshly selected native clip ID')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=60:raise ValueError('Invalid preview time')
        async with self.lock:
            result=await self._call('hold_wear_preview_pose',{'expected_wear':expected_wear,'clip_id':clip_id,'seconds':seconds})
            if result['wear_token']!=expected_wear or result['clip_id']!=clip_id or result['pose_held'] is not True or result['director_paused'] is not True:
                raise ValueError('Native frozen preview identity/state changed')
            if any(type(result[key]) not in (int,float) or not math.isfinite(result[key]) for key in ('seconds','clip_time')):
                raise ValueError('Nonfinite native preview time readback')
            if abs(result['seconds']-seconds)>1e-5 or abs(result['clip_time']-seconds)>1e-5:
                raise ValueError('Native preview time readback mismatch')
            return result

    async def pose_wear_preview_legs(self,expected_wear:str,clip_id:str,seconds:float,upper_leg_inward_degrees:float,foot_inward_degrees:float)->dict:
        if not isinstance(clip_id,str) or not re.fullmatch('0x[0-9a-fA-F]+',clip_id):raise ValueError('Use a fresh native preview clip ID')
        for name,value,maximum in [('seconds',seconds,60),('upper leg',upper_leg_inward_degrees,6),('foot',foot_inward_degrees,12)]:
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=maximum:raise ValueError('Invalid '+name)
        if upper_leg_inward_degrees>foot_inward_degrees:raise ValueError('Upper leg twist exceeds total foot yaw')
        async with self.lock:
            result=await self._call('pose_wear_preview_legs',dict(expected_wear=expected_wear,clip_id=clip_id,seconds=seconds,upper_leg_inward_degrees=upper_leg_inward_degrees,foot_inward_degrees=foot_inward_degrees))
            if result['wear_token']!=expected_wear or result['clip_id']!=clip_id or result['director_paused'] is not True or result['session_only'] is not True:raise ValueError('Preview pose identity/state changed')
            if not math.isfinite(result['clip_time']) or abs(result['clip_time']-seconds)>1e-5:raise ValueError('Preview pose time mismatch')
            return result

    async def inspect_wear_body_occlusion(self,expected_wear: str) -> dict:
        from .wear_occlusion import describe
        async with self.lock:
            data=await self._call('inspect_wear_body_occlusion',{'expected_wear':expected_wear})
            if data['wear_token']!=expected_wear:raise ValueError('Native wear identity changed')
            return describe(data)

    async def inspect_wear_native_shoes(self,expected_wear:str)->dict:
        from .native_shoe_visibility import describe
        async with self.lock:
            data=await self._call('inspect_wear_native_shoes',{'expected_wear':expected_wear})
            if data['wear_token']!=expected_wear:raise ValueError('Native wear identity changed')
            return describe(data)

    async def set_wear_native_shoes_visible(self,expected_wear:str,expected_visibility_token:str,visible:bool)->dict:
        from .native_shoe_visibility import describe,prepare
        async with self.lock:
            data=await self._call('inspect_wear_native_shoes',{'expected_wear':expected_wear})
            if data['wear_token']!=expected_wear:raise ValueError('Native wear identity changed')
            args=prepare(data,expected_visibility_token,visible)
            if args['hidden_vertices']==data['hidden_vertices']:return {'changed':False,**describe(data)}
            try:result=await self._call('set_wear_native_shoes_visible',args)
            except Exception as error:
                if 'NATIVE_SHOE_MUTATION_UNCERTAIN' in str(error):self.uncertain=True
                raise
            if result['hidden_vertices']!=args['hidden_vertices']:
                self.uncertain=True;raise RuntimeError('Native shoe visibility readback failed; do not retry')
            return result

    async def set_wear_body_occlusion(self,expected_wear: str,expected_occlusion_token: str,hidden_vertices: list[int]) -> dict:
        from .wear_occlusion import prepare,describe
        async with self.lock:
            data=await self._call('inspect_wear_body_occlusion',{'expected_wear':expected_wear})
            if data['wear_token']!=expected_wear:raise ValueError('Native wear identity changed')
            args=prepare(data,expected_occlusion_token,hidden_vertices)
            if hidden_vertices==data['hidden_vertices']:return {'changed':False,**describe(data)}
            try:result=await self._call('set_wear_body_occlusion',args)
            except Exception as error:
                if 'BODY_MASK_MUTATION_UNCERTAIN' in str(error):self.uncertain=True
                raise
            if result['hidden_vertices']!=hidden_vertices:
                self.uncertain=True;raise RuntimeError('Body occlusion readback failed; inspect saved state before another mutation')
            return result

    async def inspect_wear_fit_context(self,expected_wear: str,item_id: str,mesh_names: list[str],region: str='feet',preview: bool=False,sample_limit: int=256,target_mesh_name: str|None=None) -> dict:
        from .wear_fit import inspect,glb
        from .wear_paths import wear_destination
        if region not in ('feet','waist_back','head','whole_body'):raise ValueError('Unsupported fit region')
        if type(sample_limit) is not int or not 32<=sample_limit<=2048:raise ValueError('sample_limit must be 32..2048')
        if not isinstance(mesh_names,list) or not 1<=len(mesh_names)<=16:raise ValueError('Choose 1-16 actual wearable mesh names')
        if target_mesh_name is not None and (target_mesh_name not in mesh_names or len(mesh_names)<2):raise ValueError('Include target mesh and at least one comparison mesh')
        base_names=['Body','Foot'] if region=='feet' else ['Body'] if region=='waist_back' else ['Body','Face','Hair']
        captured=await self.capture_wear_reference(expected_wear,item_id,mesh_names,preview,True,base_names)
        data=json.loads(pathlib.Path(captured['path']).read_text(encoding='utf8'))
        report,meshes=await asyncio.to_thread(inspect,data,region,sample_limit,target_mesh_name)
        debug=wear_destination(self.lab,'fit-context-'+uuid.uuid4().hex+'.glb','.glb')
        payload=await asyncio.to_thread(glb,meshes)
        with debug.open('xb') as stream:stream.write(payload)
        report.update(raw_reference=captured,debug_glb={'path':str(debug),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'scope':'Static diagnostic anatomy and wearable geometry; no textures or animation'})
        destination=wear_destination(self.lab,'fit-context-'+uuid.uuid4().hex+'.json','.json')
        encoded=json.dumps(report,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
        with destination.open('xb') as stream:stream.write(encoded)
        return {**report,'report_path':str(destination),'report_sha256':hashlib.sha256(encoded).hexdigest()}

    async def capture_wear_review(self, expected_wear: str, views: list[str], size: int, quality: str = 'balanced') -> tuple[dict,list[bytes]]:
        quality_plan(size,quality)
        validate_wear_views(views)
        if type(size) is not int or not 256<=size<=2048:raise ValueError('Capture size must be 256..2048')
        capture_id=uuid.uuid4().hex;folder=review_folder(self.lab,capture_id)
        async with self.lock:
            state=await self._call('get_wear_snapshot',{'expected_wear':expected_wear})
            framing_reference=await self._call('wear_framing_reference',{'expected_wear':expected_wear}) if any(is_regional(v) for v in views) else None
            folder.mkdir(parents=True,exist_ok=False)
            images=[];records=[]
            for view in views:
                result=await self._call('wear_capture',{'expected_wear':expected_wear,'view':view,'size':size,'quality':quality,'framing_reference':framing_reference})
                data=decode_capture(result,size,quality);result.pop('base64')
                path=folder/(view+'.png');path.write_bytes(data);images.append(data)
                records.append({**result,'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
            manifest={'schema':'vroid-wear-review-v1','capture_id':capture_id,'wear_token':expected_wear,
                'snapshot':state,'quality':quality,'images':records,'scope':'Native assembled static views; animation/VRM/Godot separate'}
            if framing_reference:manifest['framing_reference']=framing_reference
            (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
            return manifest,images

    async def capture_wear_motion(self, expected_wear: str, samples: int, interval_seconds: float, view: str, size: int, quality: str = 'balanced') -> dict:
        quality_plan(size,quality)
        from .wear_motion import summarize_motion
        if type(samples) is not int or not 3<=samples<=16:raise ValueError('Motion sample count must be 3..16')
        if type(interval_seconds) not in (int,float) or not math.isfinite(interval_seconds) or not .1<=interval_seconds<=2:raise ValueError('Motion interval must be 0.1..2 seconds')
        validate_wear_views([view])
        if type(size) is not int or not 256<=size<=1024:raise ValueError('Motion image size must be 256..1024')
        folder=review_folder(self.lab,uuid.uuid4().hex);records=[];fixed=None
        async with self.lock:
            status=await self._call('get_wear_status')
            if status['wear_token']!=expected_wear:raise ValueError('STALE_WEAR')
            if not status['animation_playing'] or not status['animation_ready']:raise ValueError('Start native animation before capturing motion')
            folder.mkdir(parents=True,exist_ok=False);started=time.monotonic()
            for i in range(samples):
                if i:await asyncio.sleep(interval_seconds)
                result=await self._call('wear_motion_sample',{'expected_wear':expected_wear,'view':view,'size':size,'fixed_bounds':fixed,'quality':quality})
                data=decode_capture(result,size,quality);result.pop('base64')
                fixed=result['bounds'];path=folder/('frame-%02d.png'%i);path.write_bytes(data)
                records.append({**result,'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'elapsed_seconds':time.monotonic()-started})
            final=await self._call('get_wear_status')
            if final['wear_token']!=expected_wear or not final['animation_playing']:raise RuntimeError('Native motion state changed during capture')
        summary=summarize_motion(records)
        manifest={'schema':'vroid-wear-motion-v1','wear_token':expected_wear,'view':view,
            'requested_interval_seconds':interval_seconds,'size':size,'quality':quality,'samples':records,'summary':summary,
            'animation_left_playing':True,'manifest_path':str(folder/'motion.json')}
        (folder/'motion.json').write_text(json.dumps(manifest,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf8')
        return {k:v for k,v in manifest.items() if k!='samples'} | {'images':[
            {k:s[k] for k in ('frame','path','sha256','elapsed_seconds','width','height','quality','framing') if k in s} for s in records]}

    async def _wear_task(self, task: dict) -> None:
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:
                result=await self._call('task_status',task)
            except Exception as error:
                if 'MAIN_THREAD_TIMEOUT: not executed' not in str(error):
                    raise
                continue  # Read-only polling; never repeat the submitted mutation.
            if result['completed']:
                if result['faulted'] or result['canceled'] or result.get('result') is False:
                    raise RuntimeError(result.get('error','Wear operation canceled'))
                return
            await asyncio.sleep(.2)
        self.uncertain=True
        raise TimeoutError('Wear operation still pending; restart before further edits')

    async def open_wear_project(self, filename: str, expected_wear: str, discard_unsaved: bool) -> dict:
        from .wear_paths import wear_input
        path=wear_input(self.lab,filename,('.vroid','.xroid'))
        async with self.lock:
            await self._wear_task(await self._call('open_wear_project',{'path':str(path),
                'expected_wear':expected_wear,'discard_unsaved':discard_unsaved}))
            status=await self._call('get_wear_status')
            if not status['active']:raise RuntimeError('Dress-up did not become active')
            return status

    async def wear_edit(self, operation: str, args: dict) -> dict:
        if operation not in ('set_wear_fit','set_wear_animation'):
            raise ValueError('Unsupported wear edit')
        async with self.lock:
            await self._call(operation,args)
            deadline=time.monotonic()+15
            while True:
                await asyncio.sleep(.2)
                result=await self._call('get_wear_status')
                if operation!='set_wear_animation' or result['animation_playing']==args['playing'] and (not args['playing'] or result['animation_ready']):
                    return result
                if time.monotonic()>deadline:
                    raise RuntimeError('WEAR_PREVIEW_NOT_READY: native preview did not reach requested state; inspect the copy before further edits')

    async def import_xwear(self, filename: str, expected_wear: str) -> dict:
        from .wear_paths import wear_input
        path=wear_input(self.lab,filename,('.xwear',))
        async with self.lock:
            before=await self._call('get_wear_status')
            task=await self._call('import_xwear',{'path':str(path),'expected_wear':expected_wear})
            try:
                await self._wear_task(task)
            finally:
                if not self.uncertain and not self.dead:
                    after=await self._call('wear_finish_import',task)
            old={item['id'] for item in before['items']}
            added=[item['id'] for item in after['items'] if item['id'] not in old]
            if not added:raise RuntimeError('Native import completed without a new wearable')
            return {**after,'added_item_ids':added,'auto_fit_applied':False,'source_path':str(path)}

    async def save_wear_project(self, filename: str, expected_wear: str) -> dict:
        from .wear_paths import wear_destination
        import zipfile
        destination=wear_destination(self.lab,filename)
        staging=destination.parent/('stage-'+uuid.uuid4().hex+'.xroid')
        async with self.lock:
            task=await self._call('save_wear_project',{'path':str(staging),'expected_wear':expected_wear})
            await self._wear_task(task)
            if not staging.is_file() or not zipfile.is_zipfile(staging):
                raise RuntimeError('Native save did not create an XRoid archive')
            with zipfile.ZipFile(staging) as archive:
                if archive.testzip() is not None:raise RuntimeError('XRoid archive CRC failure')
            await self._call('wear_clear_save_path',{'expected_wear':expected_wear})
            os.rename(staging,destination)  # Windows refuses an existing destination.
            return {'saved':True,'path':str(destination),'bytes':destination.stat().st_size,
                'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'wear_token':expected_wear,
                'cache_path':task.get('cache_path')}

    async def export_wear_vrm(self, filename: str, expected_wear: str, title: str, author: str, version: str='1.0') -> dict:
        from .wear_paths import wear_destination
        from .vrm_export import export_metadata,validate_vrm
        metadata=export_metadata(title,author,version)
        destination=wear_destination(self.lab,filename,'.vrm')
        staging=destination.parent/('stage-'+uuid.uuid4().hex+'.vrm')
        async with self.lock:
            await self._call('prepare_wear_vrm_export',{'expected_wear':expected_wear})
            complete=False
            try:
                deadline=time.monotonic()+60
                while True:
                    state=await self._call('wear_vrm_export_state',{'expected_wear':expected_wear})
                    if state['wear_token']!=expected_wear or state['mode']!=3:raise RuntimeError('Native export identity or mode changed')
                    if state['ready'] and state['renderers']>0:break
                    if time.monotonic()>deadline:
                        self.uncertain=True
                        raise TimeoutError('Native VRM preparation pending; inspect before another operation')
                    await asyncio.sleep(.2)
                task=await self._call('write_wear_vrm_export',{'expected_wear':expected_wear,'path':str(staging),**metadata})
                await self._wear_task(task)
                complete=True
                if not staging.is_file():raise RuntimeError('Native exporter completed without a VRM file')
                checked=validate_vrm(staging)
                if checked['metadata']['name']!=title or checked['metadata']['authors']!=[author] or checked['metadata'].get('version')!=version:
                    raise RuntimeError('Native VRM metadata readback mismatch')
            except Exception:
                if not complete:
                    # Preparation may own a live native task even when polling fails.
                    self.uncertain=True
                raise
            finally:
                if complete and not self.uncertain and not self.dead:
                    cleanup=await self._call('finish_wear_vrm_export',{'expected_wear':expected_wear})
            final=await self._call('get_wear_status')
            if final['wear_token']!=expected_wear or final['animation_playing']:raise RuntimeError('Wear state changed during export')
            os.rename(staging,destination)
            return {'exported':True,'path':str(destination),'wear_token':expected_wear,**checked,
                'metadata_policy':'restrictive_native_defaults','cleanup':cleanup,'visual_fit_accepted':False,'godot_accepted':False}

    async def reopen_for_test(self, path: pathlib.Path) -> dict:
        resolved=path.resolve()
        if not resolved.is_relative_to(self.lab) or not resolved.is_file():raise ValueError('Only lab models may be opened')
        async with self.lock:
            await self._task(await self._call('open_model',{'path':str(resolved)}))
            return await self._settle()

    def close(self) -> None:
        # Kill only the process returned by this instance's spawn. No name-based attach/kill.
        try:
            if self.pid is not None and self.device is not None and not self.dead:
                try:self.device.kill(self.pid)
                except frida.ProcessNotFoundError:pass
        finally:
            self.dead=True
            if self.file_lock:
                import msvcrt
                self.file_lock.seek(0);msvcrt.locking(self.file_lock.fileno(),msvcrt.LK_UNLCK,1)
                self.file_lock.close();self.file_lock=None
