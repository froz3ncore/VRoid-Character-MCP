"""Serialized exact group discovery, registered imports and silhouette workflows."""
import asyncio
from pathlib import Path
import time

from .custom_item_file import inspect_custom_item, resolve_registered, pinned_application
from .file_paths import file_input
from .group_validation import validate_changes
from .silhouette import validate_size, solve


class GroupTools:
    async def _group_read(self, operation, expected_model, **args):
        if not isinstance(expected_model, str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED')
        result = await self._call(operation, {'expected_model': expected_model, **args})
        if result.get('model_token') != expected_model:
            raise ValueError('STALE_MODEL')
        return result

    async def list_groups(self, expected_model):
        async with self.lock:
            return await self._group_read('list_groups', expected_model)

    async def list_group_parameters(self, expected_model, group_id, kind=None):
        async with self.lock:
            return await self._group_read('list_group_parameters', expected_model, group_id=group_id, kind=kind)

    async def list_sections(self, expected_model):
        async with self.lock:
            return await self._group_read('list_sections', expected_model)

    async def list_categories(self, expected_model, section=None):
        async with self.lock:
            return await self._group_read('list_categories', expected_model, section=section)

    async def enter_category(self, expected_model, section, category):
        async with self.lock:
            return await self._group_read('enter_category', expected_model, section=section, category=category)

    async def set_group_parameters(self, expected_model, group_id, changes):
        async with self.lock:
            listed = await self._group_read('list_group_parameters', expected_model, group_id=group_id)
            validate_changes(listed['parameters'], changes)
            dispatched = False
            try:
                # New raw bones can affect body topology even outside Body UI.
                self.body_edited_tokens.add(expected_model)
                dispatched = True
                result = await self._call('set_group_parameters', {'expected_model': expected_model,
                    'group_id': group_id, 'changes': changes})
                await self._settled_for(expected_model, result.get('frame', -1))
                result['readback'] = await self._group_read('list_group_parameters', expected_model, group_id=group_id)
                result['settled'] = True
                return result
            except BaseException:
                if dispatched:
                    self.uncertain = True
                raise

    async def remove_items(self, expected_model, group):
        if not isinstance(group, str) or not group:
            raise ValueError('Exact group ID or full native type required')
        async with self.lock:
            before = await self._group_read('list_groups', expected_model)
            if before.get('membership_complete') is not True:
                raise ValueError('GROUP_MEMBERSHIP_INCOMPLETE: ' + str(before.get('errors', [])))
            exact = [row for row in before['groups'] if row['id'] == group]
            selected = exact or [row for row in before['groups'] if row['type'] == group]
            if not selected:
                raise ValueError('UNKNOWN_GROUP: use an exact ID or full native type')
            if any(row.get('removable') is not True for row in selected):
                raise ValueError('NONREMOVABLE_OR_MANDATORY_GROUP: native clear capability required')
            outcomes = []
            for index, row in enumerate(selected):
                dispatched = False
                current = None
                try:
                    self.body_edited_tokens.add(expected_model)
                    dispatched = True
                    started = await self._call('remove_group', {'expected_model': expected_model,
                        'group_id': row['id'], 'group_fingerprint': row.get('fingerprint')})
                    deadline = time.monotonic() + 30
                    while True:
                        await self._settled_for(expected_model, started.get('frame', -1))
                        current = await self._group_read('list_groups', expected_model)
                        if current.get('membership_complete') is not True:
                            raise RuntimeError('REMOVE_GROUP_UNCONFIRMED: native membership discovery incomplete')
                        ids = {g['id'] for g in current['groups']}
                        if not ids.intersection(started.get('expected_removed_ids', [row['id']])):
                            outcomes.append(dict(group_id=row['id'], removed=True, remaining_groups=current['groups'],
                                membership_complete=True,source_completeness=current.get('source_completeness'),
                                discovery_errors=current.get('errors', []),
                                native_command='RemoveTransferableGroupAndChildren',
                                verification='requested exact group absent; fresh full inventory returned; descendant IDs not independently established'))
                            break
                        if time.monotonic() >= deadline:
                            raise TimeoutError('REMOVE_GROUP_UNCONFIRMED: do not retry')
                        await asyncio.sleep(.1)
                except asyncio.CancelledError:
                    if dispatched:
                        self.uncertain = True
                    raise
                except Exception as error:
                    if dispatched:
                        self.uncertain = True
                    outcomes.append(dict(group_id=row['id'], removed=False, uncertain=dispatched,
                        unconfirmed=dispatched,error=str(error),remaining_groups=(current or {}).get('groups'),
                        membership_complete=(current or {}).get('membership_complete', False),
                        source_completeness=(current or {}).get('source_completeness'),
                        discovery_errors=(current or {}).get('errors', [])))
                    outcomes.extend(dict(group_id=g['id'], removed=False, skipped=True) for g in selected[index+1:])
                    break
            return dict(model_token=expected_model, ok=all(o.get('removed') for o in outcomes),
                        partial=any(o.get('removed') for o in outcomes) and not all(o.get('removed') for o in outcomes),
                        outcomes=outcomes, uncertain=self.uncertain)

    async def apply_custom_item(self, expected_model, filename):
        # Catalog wrappers must pass their resolved registered identity, not an
        # arbitrary path registered behind the user's back.
        path = file_input(self.lab, filename, ('.vroidcustomitem',), attached=self.mode == 'attached')
        info = inspect_custom_item(path)
        async with self.lock:
            snapshot = await self._group_read('custom_item_state', expected_model)
            row = resolve_registered(info, snapshot['files'])
            registered_path = Path(row['path']).resolve(strict=True)
            root = Path(snapshot['base_path']).resolve(strict=True)
            if not registered_path.is_relative_to(root):
                raise ValueError('CUSTOM_ITEM_PATH_OUTSIDE_REGISTRY')
            if self.mode != 'attached' and not root.is_relative_to((self.lab / 'profile').resolve()):
                raise ValueError('CUSTOM_ITEM_PROFILE_MISMATCH')
            args = {'expected_model': expected_model, 'registered_item': row,
                    'metadata': info['metadata'], 'sha256': info['sha256']}
            dispatched, receipt = False, None
            validation_dispatched, validation_terminal, primary_error = False, False, None
            with pinned_application(self, registered_path):
                if inspect_custom_item(registered_path)['sha256'] != info['sha256']:
                    raise ValueError('CUSTOM_ITEM_CHANGED')
                try:
                    # The reader may start even if dispatch loses its reply.
                    # Validation lifetime is independent of model mutation.
                    validation_dispatched = True
                    result = await self._group_read('custom_item_validate_begin', expected_model,
                        registered_item=row, metadata=info['metadata'])
                    receipt = result['request_id']
                    deadline = time.monotonic() + 30
                    while not result.get('completed'):
                        if time.monotonic() >= deadline:
                            self.uncertain = True
                            raise TimeoutError('CUSTOM_ITEM_VALIDATION_UNCONFIRMED')
                        await asyncio.sleep(.1)
                        result = await self._group_read('custom_item_validate_poll', expected_model,
                                                       request_id=receipt)
                    validation_terminal = result.get('completed') is True
                    if not result.get('compatible'):
                        raise ValueError('CUSTOM_ITEM_INCOMPATIBLE: ' + str(result.get('error')))
                    if inspect_custom_item(registered_path)['sha256'] != info['sha256']:
                        raise ValueError('CUSTOM_ITEM_CHANGED')
                    self.body_edited_tokens.add(expected_model)
                    dispatched = True
                    started = await self._call('apply_registered_custom_item', {**args, 'request_id': receipt})
                    deadline = time.monotonic() + 30
                    while True:
                        await self._settled_for(expected_model, started.get('frame', -1))
                        current = await self._group_read('list_groups', expected_model)
                        active = [g for g in current['groups'] if g['id'] == row['id'] and g.get('active')]
                        if len(active) == 1 and active[0].get('resource_name') == row['resource_name'] and active[0].get('revision') == row['revision']:
                            lifetime = await self._group_read('custom_item_application_state', expected_model,
                                                             request_id=receipt)
                            if lifetime.get('completed'):
                                return dict(model_token=expected_model, applied=True, registered_item=row,
                                    sha256=info['sha256'], input_path=str(path), native_compatibility=result,
                                    readback=active[0], native_completion=lifetime,settled=True)
                        if time.monotonic() >= deadline:
                            raise TimeoutError('CUSTOM_ITEM_APPLICATION_UNCONFIRMED')
                        await asyncio.sleep(.1)
                except BaseException as error:
                    primary_error = error
                    if dispatched or (validation_dispatched and not validation_terminal):
                        self.uncertain = True
                    raise
                finally:
                    # Retain in-flight tasks on uncertain cancellation; never
                    # release native state which may still be in use.
                    if receipt and validation_terminal and not self.uncertain:
                        try:
                            await self._call('custom_item_validate_release', {'expected_model': expected_model,
                                                                            'request_id': receipt})
                        except BaseException as cleanup_error:
                            self.uncertain = True
                            if not hasattr(self, '_custom_item_cleanup_errors'):
                                self._custom_item_cleanup_errors = []
                            self._custom_item_cleanup_errors.append({'request_id':receipt,'error':str(cleanup_error)})
                            if primary_error is None:
                                raise
                            primary_error.add_note('Custom-item cleanup failed; native lifetime retained: ' + str(cleanup_error))

    async def set_body_size(self, expected_model, height_cm, weight_kg=None, variant='F00'):
        validate_size(height_cm, weight_kg, variant)
        if not isinstance(expected_model, str) or not expected_model:
            raise ValueError('EXPECTED_MODEL_REQUIRED')
        async with self.lock:
            await self._settled_for(expected_model)
            return await solve(self, expected_model, height_cm, weight_kg, variant)

    async def _preserve_material_preset(self, area, expected_model, preset_id):
        args = {'area': area, 'expected_model': expected_model, 'preset_id': preset_id}
        # Native module prevalidates owned/simple builtin loader capability and
        # captures exact color owner/path identities before dispatch.
        dispatched = False
        try:
            dispatched = True
            result = await self._call('apply_preserving_preset', args)
            deadline = time.monotonic() + 30
            while True:
                await self._settled_for(expected_model, result.get('frame', -1))
                current = await self._call('preserving_preset_state', {**args, 'request_id': result['request_id']})
                if current.get('completed'):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('PRESET_PRESERVATION_UNCONFIRMED')
                await asyncio.sleep(.1)
            restoration = await self._call('restore_preset_materials', {**args, 'request_id': result['request_id']})
            await self._settled_for(expected_model, restoration.get('frame', -1))
            readback = await self._call('preserved_preset_readback', {**args, 'request_id': result['request_id']})
            readback.update(model_token=expected_model, preset_id=preset_id, settled=True,
                preserve_material=True, native_preserve_flag=True,
                all_materials_preserved=False,
                coverage='exact compatible discovered color paths only; texture/material channels unverified')
            return readback
        except BaseException:
            if dispatched:
                self.uncertain = True
            raise
