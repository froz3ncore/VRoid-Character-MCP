"""Isolated situation gallery, adapted from mcjo79 vroid_mcp.py cache_build.

Source 0dc7d5eb3cf27f7f943713960cac1b65f479a876 (MIT, see
licenses/mcjo79-0dc7d5e.txt). Uses the existing bridge and native selectors.
The MCP session gate and one runtime lock cover the entire transaction; internal
lock-held phases never call ready wrappers or reacquire the runtime lock.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from pathlib import Path
import uuid

from .catalog_framing import category as validate_category
from .capture_quality import decode_capture
from .custom_item_file import inspect_custom_item, pinned_application
from .preset_catalog import PresetCatalog, MAX_ROWS
from .lab_paths import _physical


def _identity(group):
    return tuple(group.get(k) for k in ('id','type','resource_name','revision'))


_KEEP={'BaseHair','BodySkin','WholeBody','Arm','Chest','Hand','Head','Leg','Neck','Shoulder','Torso','Waist',
       'FaceSkin','Eye','Eyes','Iris','Eyeball','Eyebrow','Eyelash','Eyeline','Eyelid','EyeHighlight','EyeWhite',
       'Mouth','MouthLine','Nose','Ear','Ears','Cheek','Highlight','Shadow','Lip','NoseLighting','FacePaint',
       'FaceSet','EyeSet','EyeballSet','Body'}
_STRIP={'AllHair','HairFront','HairBack','HairTied','HairSideburns','HairHanege','HairAhoge','HairSet',
        'Tops','Bottoms','Onepiece','Shoes','Socks','InnerTop','InnerBottom','ClothingSet',
        'ArmAccessory','NeckAccessory','AccessoryArm','AccessoryNeck','Attachment','Hat','AnimalEar','Tail','Glasses'}


def _slot_policy(group):
    # Suffixes in foreign namespaces cannot authorize anatomy retention. Unknown
    # full native types require an explicit reviewed policy before publication.
    match=re.fullmatch(r'TransferableGroupType\.N00\.Level[0-9]+\.([A-Za-z0-9]+)',group['type'])
    slot=match[1] if match else None
    if slot in _KEEP:return 'keep'
    if slot in _STRIP:return 'strip'
    raise ValueError('SITUATION_UNKNOWN_SLOT_POLICY: '+str(_identity(group)))


def validate_situation_request(expected_model, category, disposable_model=False, refresh=False, limit=None):
    if disposable_model is not True:raise ValueError('DISPOSABLE_MODEL_ACKNOWLEDGEMENT_REQUIRED')
    if (not isinstance(expected_model,str) or not expected_model.strip() or type(refresh) is not bool
            or limit is not None and (type(limit) is not int or not 1<=limit<=MAX_ROWS)):
        raise ValueError('INVALID_SITUATION_ARGUMENTS')
    validate_category(category)


def _capture_proof(effective, requested):
    if (not isinstance(effective,dict) or effective.get('schema')!='vroid-situation-framing-v1'
            or effective.get('requested_profile')!=requested
            or effective.get('camera_readback_verified') is not True
            or type(effective.get('source_renderer_count')) is not int or effective['source_renderer_count']<1
            or not isinstance(effective.get('source_root_id'),str) or not effective['source_root_id']):
        raise ValueError('SITUATION_FRAMING_UNVERIFIED')
    bounds=effective.get('source_bounds',{})
    for key in ('min','max'):
        if (not isinstance(bounds.get(key),list) or len(bounds[key])!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in bounds[key])):
            raise ValueError('SITUATION_BOUNDS_UNVERIFIED')
    if any(a>=b for a,b in zip(bounds['min'],bounds['max'])):
        raise ValueError('SITUATION_BOUNDS_UNVERIFIED')


class SituationTools:
    async def measure_model(self, expected_model):
        if not isinstance(expected_model,str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED')
        async with self.lock:
            await self._settled_for(expected_model)
            geometry=await self._group_read('capture_framing_reference',expected_model)
            native=await self._group_read('get_height',expected_model)
            await self._settled_for(expected_model)
            return dict(geometry,native_height=native,
                        measurement='active current ModelOrigin subtree; enabled renderers; world metres')

    async def _situation_inventory(self, expected):
        await self._settled_for(expected)
        result=await self._group_read('list_groups',expected)
        if result.get('membership_complete') is not True:
            raise ValueError('SITUATION_GROUP_MEMBERSHIP_INCOMPLETE')
        groups=[g for g in result['groups'] if g.get('active')]
        if any(not all(isinstance(g.get(k),str) and g[k] for k in
                   ('id','type','resource_name','revision')) for g in groups):
            raise ValueError('SITUATION_GROUP_IDENTITY_UNAVAILABLE')
        return groups

    async def _strip_situation(self, expected):
        removed=[]
        # Re-enumerate after every native clear: defaults can regenerate. Each
        # exact clear is attempted once; persistent/regenerated groups fail shut.
        attempted=set()
        for _ in range(512):
            groups=await self._situation_inventory(expected)
            forbidden=[g for g in groups if _slot_policy(g)=='strip']
            candidates=[g for g in forbidden if g.get('removable') is True]
            if not candidates:
                if forbidden:raise ValueError('SITUATION_FORBIDDEN_SLOT_NOT_REMOVABLE: '+str(forbidden))
                return groups,removed
            row=candidates[0]
            if row['fingerprint'] in attempted:
                raise ValueError('SITUATION_STRIP_REGENERATED_GROUP')
            attempted.add(row['fingerprint'])
            result=await self._remove_items_unlocked(expected,row['id'])
            if result.get('ok') is not True:
                raise RuntimeError('SITUATION_STRIP_FAILED: '+str(result))
            removed.append(deepcopy(row))
        raise ValueError('SITUATION_STRIP_WORK_LIMIT')

    async def _apply_situation(self, expected, row):
        # Opaque preset IDs are from this run's complete sync, never reused
        # across the restoration/reopen generation boundary.
        if row['kind']=='custom':
            info=inspect_custom_item(row['path'])
            if info['sha256']!=row.get('sha256'):
                raise ValueError('CUSTOM_ITEM_BYTES_OR_IDENTITY_CHANGED')
            result=await self._apply_custom_item_unlocked(expected,row['path'],catalog_row=row)
            registered=result['registered_item']
            if (registered['id']!=row['id'] or registered['resource_name']!=row['resource_name']
                    or registered['custom_resource_name']!=row['resource']
                    or registered['revision']!=row['revision']
                    or registered['custom_revision']!=row['custom_revision']):
                raise ValueError('SITUATION_CUSTOM_IDENTITY_CHANGED')
            return
        ids=row.get('selectable_preset_ids',[])
        if not ids or row.get('area') not in ('face','body','hair','clothing'):
            raise ValueError('SITUATION_SELECTABLE_IDENTITY_UNAVAILABLE')
        options=await self._owned_catalog(expected,row['area'],[ids[0]])
        option=options[ids[0]]
        if (option.get('resource_name')!=row['resource'] or option.get('transferable_id')!=row['id']
                or option.get('owned') is not True):
            raise ValueError('SITUATION_PRESET_IDENTITY_CHANGED')
        try:
            result=await self._apply_preset_unlocked(row['area'],expected,ids[0])
        except BaseException:
            self.uncertain=True
            raise
        if result.get('selected') is not True:
            raise ValueError('SITUATION_SELECTION_UNCONFIRMED: expanded sets need exact member evidence')

    async def _restore_situation(self, expected, saved):
        if self.dead or self.uncertain:return {'state':'skipped-uncertain'}
        try:
            await self._settled_for(expected)
        except Exception as error:
            return {'state':'skipped-model-changed','error':str(error)}
        path=Path(saved['path'])
        try:
            # Keep exact snapshot bytes stable through the native import task;
            # an uncertain import retains the same pin until explicit teardown.
            with pinned_application(self,path):
                if hashlib.sha256(path.read_bytes()).hexdigest()!=saved['sha256']:
                    return {'state':'snapshot-changed'}
                await self._settled_for(expected)
                try:
                    if path.resolve()!=path or not path.is_relative_to(self.lab):
                        raise ValueError('SITUATION_SNAPSHOT_PATH_CHANGED')
                    task=await self._call('replace_with_file',{'expected_model':expected,
                        'discard_unsaved':True,'path':str(path)})
                    await self._task(task)
                    fresh=await self._settle()
                    if not fresh.get('model_token') or fresh['model_token']==expected:
                        raise RuntimeError('CHARACTER_SWITCH_IDENTITY_UNCONFIRMED')
                except BaseException:
                    self.uncertain=True
                    raise
            return {'state':'restored','model_token':fresh['model_token'],
                    'snapshot_path':str(path),'snapshot_sha256':saved['sha256'],
                    'history_preserved':False,'original_file_association_preserved':False}
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return {'state':'failed','error':str(error)}

    async def build_preset_thumbnails(self, expected_model, category, disposable_model=False,
                                       refresh=False, limit=None):
        if self.mode!='copy' or self.owns_process is not True:
            raise ValueError('OWNED_COPY_REQUIRED')
        validate_situation_request(expected_model,category,disposable_model,refresh,limit)
        store=PresetCatalog(self.lab/'preset_cache')
        result={'processed':0,'skipped':0,'rows':[],'errors':[],'restore':{'state':'not-created'},
                'model_token':expected_model,'native_acceptance':'unverified',
                'limitations':'Current anatomy retained; native/visual/save-reopen acceptance unverified. '
                    'Snapshot restoration does not preserve original undo history, dirty state or file association.'}
        async with self.lock:
            await self._settled_for(expected_model)
            summary=await self._sync_preset_cache_unlocked(expected_model)
            framing=store.get_framing(category)
            selected=[]
            for row in store._situation_candidates(category):
                if not refresh:
                    try:
                        image,_=store.resolve_image(row['key'])
                        tested=image.get('tested',{})
                        _capture_proof(image.get('framing'),framing)
                        if (image['kind']=='situation' and image.get('verified') is True
                                and image.get('source')=='clean_fixed_camera_render'
                                and image.get('requested_framing')==framing
                                and image.get('build')==summary['source']['build']
                                and tested.get('resource')==row['resource'] and tested.get('revision')
                                and (row['kind']=='builtin' or tested['revision']==row['revision'])):
                            result['skipped']+=1;continue
                    except (ValueError,OSError):pass
                selected.append(row)
                if limit is not None and len(selected)>=limit:break
            if not selected:
                result['restore']={'state':'not-needed'};return result
            scratch=_physical(self.lab/'temp')
            scratch.mkdir(exist_ok=True)
            folder=scratch/('situation-'+uuid.uuid4().hex)
            folder.mkdir(exist_ok=False)
            result['evidence_path']=str(folder/'report.json')
            saved=None
            try:
                saved=await self._save_as_unlocked('situation-'+uuid.uuid4().hex+'.vroid',expected_model)
                result['snapshot']=saved
                await self._settled_for(expected_model)
                for row in selected:
                    evidence={'key':row['key'],'fingerprint':row['fingerprint'],'published':False}
                    result['rows'].append(evidence)
                    try:
                        baseline,removed=await self._strip_situation(expected_model)
                        evidence.update(baseline_slots=baseline,removed_slots=removed)
                        await self._apply_situation(expected_model,row)
                        active=await self._situation_inventory(expected_model)
                        group_resource=row['resource_name'] if row['kind']=='custom' else row['resource']
                        tested=[g for g in active if g['id']==row['id'] and g['resource_name']==group_resource]
                        if len(tested)!=1 or row['kind']=='custom' and tested[0]['revision']!=row['revision']:
                            raise ValueError('SITUATION_TESTED_GROUP_UNCONFIRMED')
                        # Exact single resource plus mandatory/required baseline.
                        # Expanded sets cannot use a checkbox as a member manifest.
                        tested=tested[0]
                        certificate=await self._group_read('list_groups',expected_model,
                            situation_root={k:tested[k] for k in ('id','type','resource_name','revision')})
                        if certificate.get('membership_complete') is not True:
                            raise ValueError('SITUATION_CERTIFICATE_INVENTORY_INCOMPLETE')
                        membership=certificate.get('situation_membership')
                        evidence['membership']=membership
                        if membership is not None and membership.get('verified') is not True:
                            raise ValueError('SITUATION_MEMBERSHIP_UNPROVEN: '+str(membership))
                        members=membership['members'] if membership else [tested]
                        if membership and (_identity(membership.get('root',{}))!=_identity(tested)
                                or not isinstance(members,list) or not 1<=len(members)<=512
                                or len({_identity(g) for g in members})!=len(members)
                                or _identity(tested) not in {_identity(g) for g in members}):
                            raise ValueError('SITUATION_MEMBER_CERTIFICATE_IDENTITY_CHANGED')
                        if row.get('is_set_item') and membership is None:
                            raise ValueError('SITUATION_SET_MEMBERSHIP_UNPROVEN')
                        types={g['type'] for g in members}
                        baseline_ids={_identity(g) for g in baseline if g['type'] not in types}
                        if {_identity(g) for g in active}!={_identity(g) for g in members}|baseline_ids:
                            raise ValueError('SITUATION_WRONG_REMAINING_SLOTS')
                        evidence['retained_slots']=active
                        capture=await self._native_capture({'expected_model':expected_model,'view':'front',
                            'size':512,'quality':'balanced','clean':True,'situation_framing':framing})
                        if capture.get('model_token')!=expected_model:
                            raise ValueError('MODEL_CHANGED_DURING_CAPTURE')
                        data=decode_capture(capture,512,'balanced')
                        path=folder/(str(len(result['rows']))+'.png')
                        with path.open('xb') as stream:stream.write(data)
                        evidence['capture_path']=str(path)
                        evidence['capture_metadata']={k:v for k,v in capture.items() if k!='base64'}
                        effective=capture.get('framing',{})
                        if capture.get('provenance')!='clean_fixed_camera_render':
                            raise ValueError('SITUATION_FRAMING_UNVERIFIED')
                        _capture_proof(effective,framing)
                        after=await self._situation_inventory(expected_model)
                        if {_identity(g) for g in after}!={_identity(g) for g in active}:
                            raise ValueError('SITUATION_GROUPS_CHANGED_DURING_CAPTURE')
                        metadata={'kind':'situation','source':'clean_fixed_camera_render','verified':True,
                            'tested':{**{k:row.get(k) for k in ('resource','kind','custom_revision','sha256')},
                                      'id':tested['id'],'revision':tested['revision'],'type':tested['type'],
                                      'group_resource':tested['resource_name']},'membership':membership,
                            'requested_framing':framing,'framing':effective,'orientation_yaw_degrees':framing['yaw'],
                            'quality':capture['quality'],'model_token':expected_model,'build':summary['source']['build'],
                            'captured_at':datetime.now(timezone.utc).isoformat(),
                            'retained_slots':active,'removed_slots':removed,
                            'mannequin':'current anatomy with verified removable slots stripped'}
                        evidence['image']=store.publish_image(row['key'],data,metadata,row['fingerprint'])
                        evidence['published']=True;result['processed']+=1
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        evidence['error']=str(error);result['errors'].append({'key':row['key'],'error':str(error)})
                        # Do not retry failed/uncertain rows or continue from a
                        # potentially different model. Finally retains evidence.
                        break
            except asyncio.CancelledError:
                raise
            except Exception as error:
                result['errors'].append({'phase':'snapshot','error':str(error)})
            finally:
                if saved:
                    result['restore']=await self._restore_situation(expected_model,saved)
                    if result['restore']['state']=='restored':result['model_token']=result['restore']['model_token']
                    else:
                        if result['restore']['state'] in ('failed','skipped-model-changed'):
                            result['model_token']=None
                        result['errors'].append({'phase':'restore',**result['restore']})
                result['uncertain']=self.uncertain
                (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),
                    encoding='utf-8',newline='\r\n')
        return result
