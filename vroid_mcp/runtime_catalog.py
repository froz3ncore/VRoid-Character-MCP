"""Bounded native catalog synchronization; offline persistence is separate."""
import asyncio
from copy import deepcopy
import time
import zipfile

from .custom_item_file import inspect_custom_item
from .preset_catalog import PresetCatalog, MAX_ROWS, _row


class CatalogTools:
    async def sync_preset_cache(self, expected_model, icons=False, icon_limit=None):
        if (not isinstance(expected_model,str) or not expected_model or type(icons) is not bool
                or icon_limit is not None and (type(icon_limit) is not int or not 1<=icon_limit<=200)):
            raise ValueError('INVALID_CATALOG_SYNC_ARGUMENTS')
        store = PresetCatalog(self.lab/'preset_cache')
        async with self.lock:
            await self._settled_for(expected_model)
            receipt = await self._call('preset_catalog_begin', {'expected_model':expected_model})
            request = receipt['request_id']
            release_attempted = False
            try:
                deadline = time.monotonic()+15
                while True:
                    result = await self._call('preset_catalog_poll',{'expected_model':expected_model,'request_id':request})
                    if result.get('completed'): break
                    if time.monotonic()>=deadline: raise TimeoutError('CATALOG_SCAN_TIMEOUT')
                    await asyncio.sleep(.1)
                result = deepcopy(result)
                if (result.get('model_token')!=expected_model or result.get('builtin_complete') is not True
                        or result.get('areas')!=['face','body','hair','clothing']
                        or not isinstance(result.get('build'),str) or len(result['build'])!=64
                        or not isinstance(result.get('rows'),list) or len(result['rows'])>MAX_ROWS
                        or type(result.get('custom_complete')) is not bool):
                    raise ValueError('CATALOG_NATIVE_SCAN_INCOMPLETE')
                # Finish the native receipt (including exact owner validation)
                # before slow offline ZIP work or any durable removal inference.
                await self._settled_for(expected_model)
                release_attempted = True
                released = await self._call('preset_catalog_release',{'expected_model':expected_model,'request_id':request})
                if released.get('released') is not True:
                    raise ValueError('CATALOG_NATIVE_RECEIPT_NOT_RELEASED')
                rows, errors, customs_complete, seen = [], list(result.get('errors',[])), result['custom_complete'], set()
                for row in result['rows']:
                    # Validate every identity before archive IO or catalog mutation.
                    normalized = _row(row)
                    if normalized['key'] in seen: raise ValueError('CATALOG_DUPLICATE_RESOURCE')
                    seen.add(normalized['key'])
                    if row['kind']=='custom':
                        try:
                            info=inspect_custom_item(row['path'])
                            if (info['metadata']['rootTransferableGroupId']!=row['id']
                                    or info['metadata']['rootTransferableGroupTypeId']!=row['group_type']
                                    or row.get('registered') is not True):
                                raise ValueError('CUSTOM_ITEM_REGISTRY_IDENTITY_STALE')
                            row=dict(row,sha256=info['sha256'])
                        except (ValueError,OSError) as error:
                            customs_complete=False; errors.append(str(error)); continue
                    rows.append(row)
                summary=store.sync(rows,{'build':result['build'],'session':expected_model,'scope':result.get('scope')},
                                   {'builtin':True,'custom':customs_complete})
            finally:
                if not release_attempted and not self.dead and not self.uncertain:
                    await self._call('preset_catalog_release',{'expected_model':expected_model,'request_id':request})
            images,attempts=0,0
            if icons:
                for row in rows:
                    if attempts >= (icon_limit or 50): break
                    if not row['selectable'] or not row['owned']: continue
                    attempts+=1
                    scanned=_row(row)
                    if row['kind']=='custom':
                        try:
                            info=inspect_custom_item(row['path'],include_icon=True)
                            if (info['sha256']!=row['sha256']
                                    or info['metadata']['rootTransferableGroupId']!=row['id']
                                    or info['metadata']['rootTransferableGroupTypeId']!=row['group_type']):
                                raise ValueError('CUSTOM_ITEM_BYTES_OR_IDENTITY_CHANGED')
                            data=info['icon']
                            metadata={'source':'registered-custom-archive','sha256_custom_item':row['sha256']}
                        except (ValueError,OSError,zipfile.BadZipFile) as error:
                            errors.append(str(error)); continue
                    else:
                        ids=row.get('selectable_preset_ids',[])
                        if not ids or row.get('area') not in ('face','body','hair','clothing'): continue
                        metadata,data=await self._thumbnail(expected_model,row['area'],ids[0])
                        if data is None:
                            errors.append(metadata); continue
                        if metadata.get('resource_name')!=row['resource'] or metadata.get('transferable_id')!=row['id']:
                            raise ValueError('CATALOG_ICON_RESOURCE_IDENTITY_CHANGED')
                    store.publish_image(scanned['key'],data,dict(metadata,kind='native-icon',
                                        model_token=expected_model,build=result['build']),scanned['fingerprint'])
                    images+=1
            return dict(summary,images=images,icon_attempts=attempts,errors=errors,native_acceptance='unverified')
