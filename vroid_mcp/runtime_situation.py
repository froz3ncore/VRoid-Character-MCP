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
import zipfile
import base64

from .catalog_framing import category as validate_category
from .capture_quality import decode_capture
from .custom_item_file import inspect_custom_item, pinned_application
from .preset_catalog import PresetCatalog, MAX_ROWS, capture_identity
from .lab_paths import _physical
from .situation_proof import capture_proof, raster_evidence, definition, identity
from .task_receipt import ManagedTaskFailure


def _identity(group):
    return identity(group)


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
    capture_proof(effective,requested)


def _safe_json(value):
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:_safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_safe_json(v) for v in value]
    return value


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
                   ('id','type','resource_name','revision')) or type(g.get('updated_since_last_revision')) is not bool for g in groups):
            raise ValueError('SITUATION_GROUP_IDENTITY_UNAVAILABLE')
        return groups

    async def _strip_situation(self, expected, frozen_keep, tested_types, evidence, persist):
        groups=await self._situation_inventory(expected)
        keep=[g for g in groups if _slot_policy(g)=='keep']
        if ({_identity(g) for g in keep if g['type'] not in tested_types}
                !={_identity(g) for g in frozen_keep if g['type'] not in tested_types}):
            raise ValueError('SITUATION_ORIGINAL_ANATOMY_CHANGED')
        expected_keep={_identity(g) for g in keep}
        evidence['removed_slots']=[];evidence['operations']=[];persist()
        # Re-enumerate after every native clear: defaults can regenerate. Each
        # exact clear is attempted once; persistent/regenerated groups fail shut.
        attempted=set()
        for _ in range(512):
            groups=await self._situation_inventory(expected)
            if {_identity(g) for g in groups if _slot_policy(g)=='keep'}!=expected_keep:
                raise ValueError('SITUATION_STRIP_CHANGED_REQUIRED_ANATOMY')
            forbidden=[g for g in groups if _slot_policy(g)=='strip' and g['type'] not in tested_types]
            candidates=[g for g in forbidden if g.get('removable') is True]
            if not candidates:
                if forbidden:raise ValueError('SITUATION_FORBIDDEN_SLOT_NOT_REMOVABLE: '+str(forbidden))
                return groups,evidence['removed_slots']
            row=candidates[0]
            if row['fingerprint'] in attempted:
                raise ValueError('SITUATION_STRIP_REGENERATED_GROUP')
            attempted.add(row['fingerprint'])
            operation={'phase':'clear','group':deepcopy(row),'state':'dispatching'}
            evidence['operations'].append(operation);persist()
            try:result=await self._remove_items_unlocked(expected,row['id'])
            except BaseException as error:
                operation.update(state='interrupted',error=str(error));persist();raise
            operation.update(state='returned',receipt=result);persist()
            if result.get('ok') is not True:
                raise RuntimeError('SITUATION_STRIP_FAILED: '+str(result))
            evidence['removed_slots'].append(deepcopy(row));persist()
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

    async def _restore_situation(self, expected, saved, owner, original_groups, result, persist):
        path=Path(saved['path'])
        receipt={'state':'pending','phase':'preflight','snapshot_path':str(path),'snapshot_sha256':saved['sha256'],
                 'import_dispatch':'not-sent','terminal_received':False,'terminal_status':'not-started'}
        result['restore']=receipt
        try:
            persist()
            if self.dead or self.uncertain:
                self.uncertain=True;receipt['state']='skipped-uncertain';return receipt
            try:await self._settled_for(expected)
            except asyncio.CancelledError:raise
            except Exception as error:
                self.uncertain=True;receipt.update(state='skipped-model-changed',error=str(error));return receipt
            # The generation pin is already held by the outer transaction.
            receipt['phase']='verify-snapshot';persist()
            if hashlib.sha256(path.read_bytes()).hexdigest()!=saved['sha256']:
                self.uncertain=True;receipt['state']='snapshot-changed';return receipt
            await self._settled_for(expected)
            if path.resolve()!=path or not path.is_relative_to(self.lab):raise ValueError('SITUATION_SNAPSHOT_PATH_CHANGED')
            receipt.update(phase='import-dispatching',import_dispatch='unknown',terminal_status='unknown');persist()
            task=await self._call('replace_with_file',{'expected_model':expected,'discard_unsaved':True,'path':str(path)})
            receipt.update(phase='import-dispatched',import_dispatch='sent',task=deepcopy(task));persist()
            terminal=await self._task(task)
            receipt.update(phase='terminal-received',terminal_received=True,terminal_status='succeeded')
            if isinstance(terminal,dict):receipt['terminal_receipt']=terminal
            persist()
            receipt['phase']='verify-owner';persist()
            fresh=await self._settle()
            receipt['observed_owner']=fresh;persist()
            verified=(fresh.get('model_token') and fresh['model_token']!=expected
                and isinstance(fresh.get('engine_id'),str) and fresh['engine_id']!=owner.get('engine_id')
                and isinstance(fresh.get('file_path'),str) and Path(fresh['file_path']).resolve()==path)
            if verified:
                receipt['phase']='verify-inventory';persist()
                groups=await self._situation_inventory(fresh['model_token'])
                verified={_identity(g) for g in groups}=={_identity(g) for g in original_groups}
            if not verified:
                self.uncertain=True
                receipt['state']='unconfirmed';return receipt
            receipt.update(state='restored',phase='verified',model_token=fresh['model_token'],engine_id=fresh['engine_id'],
                    associated_file=fresh['file_path'],original_inventory_verified=True,
                    history_preserved=False,original_file_association_preserved=False)
            return receipt
        except asyncio.CancelledError:
            self.uncertain=True
            receipt.update(state='pending',interrupted=True)
            persist()
            raise
        except ManagedTaskFailure as error:
            self.uncertain=True
            receipt.update(state='failed',phase='terminal-negative',terminal_received=True,terminal_status='negative',
                           terminal_receipt=error.receipt,error=str(error))
            return receipt
        except Exception as error:
            self.uncertain=True
            receipt.update(state='failed',error=str(error))
            return receipt

    async def _candidate_definition(self, expected, row):
        resource=row['resource_name'] if row['kind']=='custom' else row['resource']
        response=await self._group_read('list_groups',expected,
            situation_candidate={'id':row['id'],'resource_name':resource})
        if response.get('membership_complete') is not True:raise ValueError('SITUATION_CANDIDATE_INVENTORY_INCOMPLETE')
        value=response.get('situation_definition');root=definition(value,version=False)
        if (root['id']!=row['id'] or root['resource_name']!=resource
                or row['kind']=='custom' and root['type']!=row['group_type']):
            raise ValueError('SITUATION_CANDIDATE_IDENTITY_CHANGED')
        _slot_policy(root)
        return value

    def _cached_situation(self, store, row, framing, candidate, raster_cache):
        try:
            image,data=store._resolve_observed_image(row,raster_cache)
            if (image['kind']!='situation' or image.get('source')!='clean_fixed_camera_render'
                    or image.get('verified') is not True or image.get('capture_input')!=capture_identity(row)
                    or image.get('requested_framing')!=framing):return False,0
            decode_capture({**image,'base64':base64.b64encode(data).decode('ascii')},512,'balanced')
            _capture_proof(image.get('framing'),framing)
            digest=hashlib.sha256(data).hexdigest()
            if digest not in raster_cache:raster_cache[digest]=raster_evidence(data)
            if image.get('raster')!=raster_cache[digest]:return False,0
            try:current=definition(candidate)
            except ValueError:return False,1
            if image.get('native_definition')!=current or definition(image.get('membership'))!=current:return False,0
            root=current['root'];tested=image.get('tested',{})
            if (tested.get('resource')!=row['resource'] or any(tested.get(k)!=root[k] for k in ('id','type','revision'))
                    or tested.get('group_resource')!=root['resource_name'] or tested.get('kind')!=row['kind']
                    or row['kind']=='custom' and any(tested.get(k)!=row.get(k) for k in ('custom_revision','sha256'))):return False,0
            return True,0
        except (ValueError,KeyError,TypeError,OSError):return False,0

    async def build_preset_thumbnails(self, expected_model, category, disposable_model=False,
                                       refresh=False, limit=None):
        if self.mode!='copy' or self.owns_process is not True:raise ValueError('OWNED_COPY_REQUIRED')
        validate_situation_request(expected_model,category,disposable_model,refresh,limit)
        store=PresetCatalog(self.lab/'preset_cache')
        result={'processed':0,'skipped':0,'rows':[],'errors':[],'restore':{'state':'not-created'},
                'model_token':None,'native_acceptance':'unverified',
                'limitations':'Current anatomy retained; native/visual/save-reopen acceptance unverified. '
                    'Snapshot restoration does not preserve original undo history, dirty state or file association.'}
        async with self.lock:
            owner=await self._settled_for(expected_model)
            if not isinstance(owner.get('engine_id'),str) or not owner['engine_id']:
                raise ValueError('SITUATION_ORIGINAL_ENGINE_UNPROVEN')
            summary=await self._sync_preset_cache_unlocked(expected_model)
            observed=store._situation_snapshot(category,summary['scan_id']);framing=observed['framing']
            selected=[];raster_cache={};cache_hits=[]
            for row in observed['rows']:
                try:
                    candidate=await self._candidate_definition(expected_model,row)
                    cached,priority=self._cached_situation(store,row,framing,candidate,raster_cache) if not refresh else (False,0)
                    if cached:cache_hits.append(row);continue
                    selected.append((priority,row,candidate))
                except Exception as error:
                    result['errors'].append({'key':row['key'],'phase':'candidate','error':str(error)})
            # Regenerate unprovable old captures after genuinely missing/outdated
            # rows, so repeated small limits do not starve the rest of a category.
            selected.sort(key=lambda item:(item[0],item[1]['key']))
            if limit is not None:selected=selected[:limit]
            if not selected:
                result['restore']={'state':'not-needed'}
                result['model_token']=(await self._settled_for(expected_model))['model_token']
                try:result['skipped']=store._verify_situation_hits(observed,cache_hits,raster_cache)
                except (ValueError,OSError) as error:result['errors'].append({'phase':'cache-observation','error':str(error)})
                return result
            try:store._verify_situation_hits(observed,cache_hits,raster_cache)
            except (ValueError,OSError) as error:
                result['errors'].append({'phase':'cache-observation','error':str(error)})
                result['restore']={'state':'not-needed'}
                return result
            scratch=_physical(self.lab/'temp');scratch.mkdir(exist_ok=True)
            folder=scratch/('situation-'+uuid.uuid4().hex);folder.mkdir(exist_ok=False)
            result['evidence_path']=str(folder/'report.json')
            def persist():
                (folder/'report.json').write_text(json.dumps(_safe_json(result),ensure_ascii=False,indent=2,allow_nan=False),
                    encoding='utf-8',newline='\r\n')
            saved=None;pin=None;pin_entered=False;snapshot_verified=False;original_groups=None
            persist()
            try:
                original_groups=await self._situation_inventory(expected_model)
                frozen_keep=[deepcopy(g) for g in original_groups if _slot_policy(g)=='keep']
                result['original_owner']=owner;result['original_groups']=original_groups;persist()
                saved=await self._save_as_unlocked('situation-'+uuid.uuid4().hex+'.vroid',expected_model)
                result['snapshot']=saved;persist()
                path=Path(saved['path'])
                if path.resolve()!=path or not path.is_relative_to(self.lab):raise ValueError('SITUATION_SNAPSHOT_PATH_CHANGED')
                pin=pinned_application(self,path);pin.__enter__();pin_entered=True
                if hashlib.sha256(path.read_bytes()).hexdigest()!=saved['sha256']:
                    result['restore']={'state':'snapshot-changed'};raise ValueError('SITUATION_SNAPSHOT_HASH_CHANGED_BEFORE_MUTATION')
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None:raise ValueError('SITUATION_SNAPSHOT_CRC_FAILED')
                snapshot_verified=True;saved['generation_pin_verified']=True;persist()
                await self._settled_for(expected_model)
                for _,row,candidate in selected:
                    evidence={'key':row['key'],'fingerprint':row['fingerprint'],'published':False,
                        'candidate':candidate,'removed_slots':[],'operations':[]}
                    result['rows'].append(evidence);persist()
                    try:
                        prebound=definition(candidate,version=False)
                        try:prior_definition=definition(candidate)
                        except ValueError:prior_definition=None
                        tested_types={g['type'] for g in candidate['members']} if prior_definition else {prebound['type']}
                        baseline,removed=await self._strip_situation(expected_model,frozen_keep,tested_types,evidence,persist)
                        evidence['baseline_slots']=baseline;persist()
                        operation={'phase':'apply','state':'dispatching','id':row['id']}
                        evidence['operations'].append(operation);persist()
                        await self._apply_situation(expected_model,row)
                        operation['state']='settled';persist()
                        active=await self._situation_inventory(expected_model)
                        tested=[g for g in active if all(g[k]==prebound[k] for k in ('id','type','resource_name'))]
                        if len(tested)!=1:raise ValueError('SITUATION_TESTED_GROUP_UNCONFIRMED')
                        tested=tested[0]
                        if row['kind']=='custom' and tested['revision']!=row['revision']:raise ValueError('SITUATION_CUSTOM_REVISION_CHANGED')
                        certificate=await self._group_read('list_groups',expected_model,
                            situation_root={k:tested[k] for k in ('id','type','resource_name','revision')})
                        if certificate.get('membership_complete') is not True:raise ValueError('SITUATION_CERTIFICATE_INVENTORY_INCOMPLETE')
                        membership=certificate.get('situation_membership');evidence['membership']=membership;persist()
                        current_definition=definition(membership)
                        if (any(current_definition['root'][k]!=prebound[k] for k in ('id','type','resource_name'))
                                or prior_definition and prior_definition!=current_definition):
                            raise ValueError('SITUATION_MEMBER_VERSION_CHANGED')
                        members=current_definition['members'];types={g['type'] for g in members}
                        allowed={_identity(g) for g in frozen_keep if g['type'] not in types}|{_identity(g) for g in members}
                        if {_identity(g) for g in active}!=allowed:raise ValueError('SITUATION_WRONG_REMAINING_SLOTS')
                        evidence['retained_slots']=active;persist()
                        capture=await self._native_capture({'expected_model':expected_model,'view':'front',
                            'size':512,'quality':'balanced','clean':True,'situation_framing':framing})
                        # Retain returned bytes/metadata before any proof rejects.
                        data=base64.b64decode(capture['base64'],validate=True)
                        path=folder/(str(len(result['rows']))+'.png')
                        with path.open('xb') as stream:stream.write(data)
                        evidence['capture_path']=str(path)
                        evidence['capture_metadata']=_safe_json({k:v for k,v in capture.items() if k!='base64'});persist()
                        if capture.get('model_token')!=expected_model:raise ValueError('MODEL_CHANGED_DURING_CAPTURE')
                        decode_capture(capture,512,'balanced')
                        if capture.get('provenance')!='clean_fixed_camera_render':raise ValueError('SITUATION_FRAMING_UNVERIFIED')
                        effective=capture.get('framing');_capture_proof(effective,framing)
                        raster=raster_evidence(data)
                        after=await self._situation_inventory(expected_model)
                        if {_identity(g) for g in after}!=allowed:raise ValueError('SITUATION_GROUPS_CHANGED_DURING_CAPTURE')
                        metadata={'kind':'situation','source':'clean_fixed_camera_render','verified':True,
                            'tested':{**{k:row.get(k) for k in ('resource','kind','custom_revision','sha256')},
                                'id':tested['id'],'revision':tested['revision'],'type':tested['type'],
                                'group_resource':tested['resource_name']},'membership':membership,
                            'native_definition':current_definition,'capture_input':capture_identity(row),'raster':raster,
                            'requested_framing':framing,'framing':effective,'orientation_yaw_degrees':framing['yaw'],
                            'quality':capture['quality'],'model_token':expected_model,'build':summary['source']['build'],
                            'captured_at':datetime.now(timezone.utc).isoformat(),'retained_slots':active,'removed_slots':removed,
                            'mannequin':'current anatomy with verified removable slots stripped'}
                        evidence['image']=store.publish_image(row['key'],data,metadata,row['fingerprint'],
                            expected_situation={'scan_id':observed['scan_id'],'identity':capture_identity(row),'framing':framing})
                        evidence['published']=True;result['processed']+=1;persist()
                    except asyncio.CancelledError:
                        evidence['interrupted']=True;persist();raise
                    except Exception as error:
                        evidence['error']=str(error);result['errors'].append({'key':row['key'],'error':str(error)});persist();break
            except asyncio.CancelledError:
                result['interrupted']=True;persist();raise
            except Exception as error:
                result['errors'].append({'phase':'snapshot-or-precondition','error':str(error)});persist()
            finally:
                try:
                    if saved and snapshot_verified:
                        result['restore']=await self._restore_situation(expected_model,saved,owner,original_groups,result,persist)
                        if result['restore']['state']=='restored':result['model_token']=result['restore']['model_token']
                        else:result['errors'].append({'phase':'restore',**result['restore']})
                finally:
                    result['uncertain']=self.uncertain
                    try:
                        try:result['skipped']=store._verify_situation_hits(observed,cache_hits,raster_cache)
                        except (ValueError,OSError) as error:
                            result['skipped']=0
                            result['errors'].append({'phase':'cache-observation','error':str(error)})
                        persist()
                    finally:
                        if pin_entered:pin.__exit__(None,None,None)
        return result
