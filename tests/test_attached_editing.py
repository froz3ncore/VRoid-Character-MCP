"""Host-side boundaries for real-window recovery and profile ownership."""
import asyncio
import json
from types import SimpleNamespace
import zipfile

import pytest

from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime


def attached(tmp_path, monkeypatch, native):
    runtime = Runtime(tmp_path)
    runtime.mode = 'attached'
    runtime.native_png_decoder_ready = True
    runtime.script = SimpleNamespace(exports_sync=SimpleNamespace(call=native))
    monkeypatch.setattr(bridge.attached_ui, 'window_state', lambda pid: {'blocked': False})
    return runtime


def test_os_modal_never_dispatches_or_marks_model_confirmed(tmp_path, monkeypatch):
    calls = []
    r = attached(tmp_path, monkeypatch, lambda *a: calls.append(a))
    monkeypatch.setattr(bridge.attached_ui, 'window_state', lambda _: {'blocked': True})
    async def exercise():
        status = await r._call('status')
        assert status['current_state_unavailable'] and not status['model_ready']
        with pytest.raises(RuntimeError, match='ATTACHED_OS_MODAL_BLOCKED'):
            await r._call('undo')
    asyncio.run(exercise())
    assert not calls and not r.uncertain


def test_uncertain_attachment_allows_inspection_and_review_but_never_replays(tmp_path, monkeypatch):
    calls = []
    r = attached(tmp_path, monkeypatch, lambda op,args: calls.append(op) or {})
    r.uncertain = True
    async def exercise():
        for op in ('status','list_face_params','list_texture_layers','export_texture_layer',
                   'attached_review','attached_acknowledge'):
            await r._call(op)
        with pytest.raises(RuntimeError, match='ATTACHED_EDIT_NEEDS_REVIEW'):
            await r._call('import_texture_layer')
    asyncio.run(exercise())
    assert 'import_texture_layer' not in calls and r.uncertain


def test_attached_save_copy_checks_archive_and_never_overwrites(tmp_path):
    r = Runtime(tmp_path); r.mode = 'attached'
    async def settle(*args): return {'model_token': 'live'}
    async def call(op, args):
        assert op == 'save_as' and args['expected_model'] == 'live'
        with zipfile.ZipFile(args['path'], 'w') as archive:
            archive.writestr('model', 'x' * 200)
        return {'saved': True}
    r._settle, r._call = settle, call
    saved = asyncio.run(r.save_as('copy.vroid', 'live'))
    assert saved['attached_copy'] and zipfile.is_zipfile(saved['path'])
    with pytest.raises(FileExistsError):
        asyncio.run(r.save_as('copy.vroid', 'live'))


def test_current_to_wear_requires_switch_and_fresh_wear_before_saving():
    from vroid_mcp import tools_wear
    registered = {}
    def register(**kwargs):
        def wrap(fn): registered[fn.__name__] = fn; return fn
        return wrap
    events = []
    class FakeRuntime:
        async def wear_status(self): events.append('status'); return {'wear_token': 'fresh'}
        async def status(self): events.append('model_status'); return {'model_token': 'model', 'mode': 'copy'}
        async def save_as(self, filename, token): events.append('save'); return {'path': filename}
        async def open_wear_project(self, filename, token, discard, guard):
            events.append('open'); assert discard; return {'active': True}
    tools_wear.register(register, FakeRuntime(), None, None, None)
    tool = registered['open_current_in_wear']
    with pytest.raises(ValueError, match='EXPLICIT_SWITCH'):
        asyncio.run(tool('model', 'fresh', 'copy.vroid'))
    assert not events
    with pytest.raises(ValueError, match='STALE_WEAR'):
        asyncio.run(tool('model', 'old', 'copy.vroid', True))
    assert events == ['status']
    events.clear()
    result = asyncio.run(tool('model', 'fresh', 'copy.vroid', True))
    assert events == ['status', 'model_status', 'save', 'open'] and result['wear']['active']


def test_current_to_wear_does_not_switch_if_character_changes_after_save():
    from vroid_mcp import tools_wear
    registered = {}
    def register(**kwargs):
        def wrap(fn): registered[fn.__name__] = fn; return fn
        return wrap
    class FakeRuntime:
        checks = 0
        async def wear_status(self): return {'wear_token': 'fresh'}
        async def status(self):
            self.checks += 1
            return {'model_token': 'model', 'mode': 'attached',
                    'attached_state': {'history_revision': self.checks, 'file_path': 'original', 'unsaved': True}}
        async def save_as(self, *args): return {'path': 'copy.vroid'}
        async def open_wear_project(self, *args): raise AssertionError('must not switch')
    tools_wear.register(register, FakeRuntime(), None, None, None)
    with pytest.raises(RuntimeError, match='copy.vroid'):
        asyncio.run(registered['open_current_in_wear']('model', 'fresh', 'copy.vroid', True))


def test_attached_custom_save_uses_native_target_profile_and_keeps_dirty_flag(tmp_path, monkeypatch):
    root = tmp_path/'external-profile'/'custom_items'
    root.mkdir(parents=True)
    target = root/'new.vroidcustomitem'
    item = {'id':'custom-id','group_type':'native.Iris','path':str(target)}
    calls = []
    r = Runtime(tmp_path/'client')
    r.mode = 'attached'
    r.native_png_decoder_ready = True
    async def settle(*args): pass
    async def native(op,args=None):
        calls.append((op,args))
        if op=='status':return {'model_ready':True,'model_token':'live'}
        if op=='custom_item_state':
            return {'base_path':str(root),'source_file_path':'original.vroid','unsaved':True,
                'parts':[{'id':'active','type':'Iris','group_type':'native.Iris'}],
                'files':[item] if target.exists() else []}
        if op=='save_custom_item':
            with zipfile.ZipFile(target,'w') as z:
                z.writestr('v1customitem/meta.json',json.dumps({'rootTransferableGroupId':'custom-id',
                    'rootTransferableGroupTypeId':'native.Iris'}))
            return {}
        if op=='preserve_attached_unsaved':
            assert args['was_unsaved'] and args['source_file_path']=='original.vroid'
            return {}
        raise AssertionError(op)
    r._settle,r._call=settle,native
    result=asyncio.run(r.save_custom_items('live',['Iris']))
    assert result['profile_scope']=='attached VRoid profile'
    assert result['saved'][0]['path']==str(target)
    assert calls[-1][0]=='preserve_attached_unsaved'


def test_target_closet_root_change_is_uncertain_and_never_writes_to_new_root(tmp_path):
    r=Runtime(tmp_path/'client');r.mode='attached';r.native_png_decoder_ready=True
    root=tmp_path/'profile';root.mkdir()
    calls=[]
    async def native(op,args=None):
        calls.append(op)
        if op=='status':return {'model_ready':True,'model_token':'live'}
        if op=='custom_item_state':return {'base_path':str(root if calls.count(op)==1 else root/'changed'),
            'parts':[{'id':'part','type':'Iris','group_type':'Iris'}],'files':[]}
        return {}
    async def settle(*a):pass
    r._call,r._settle=native,settle
    with pytest.raises(RuntimeError,match='CUSTOM_ITEM_PROFILE_CHANGED'):
        asyncio.run(r.save_custom_items('live',['Iris']))
    assert calls.count('save_custom_item')==1 and r.uncertain


@pytest.mark.parametrize('outcome', ['success','partial','exception','finish_failure'])
def test_public_edit_receipt_covers_entire_verified_tool_and_preserves_original_error(tmp_path, monkeypatch, outcome):
    from vroid_mcp import server
    events=[]
    class FakeRuntime:
        def __init__(self,lab):
            self.mode='attached';self.uncertain=False
        def start(self):pass
        async def initialize(self,*a):pass
        async def _call(self,op,args):
            events.append((op,args))
            if op=='attached_edit_begin':return {'id':'receipt'}
            if outcome in ('exception','finish_failure'):raise RuntimeError('finish transport failed')
            return {'needs_review':outcome=='partial'}
        async def replace_part(self,*args):
            events.append(('native_and_verification',{}))
            if outcome=='exception':raise ValueError('original native failure')
            return {'ok':outcome!='partial'}
    monkeypatch.setattr(server,'Runtime',FakeRuntime)
    mcp=server.create_server(tmp_path,'F00')
    tool=mcp._tool_manager.get_tool('replace_part').fn
    if outcome=='exception':
        with pytest.raises(ValueError,match='original native failure'):
            asyncio.run(tool(expected_model='live',part_id='part'))
    elif outcome=='finish_failure':
        with pytest.raises(RuntimeError,match='finish transport failed'):
            asyncio.run(tool(expected_model='live',part_id='part'))
    else:
        asyncio.run(tool(expected_model='live',part_id='part'))
    assert [e[0] for e in events]==['attached_edit_begin','native_and_verification','attached_edit_finish']
    assert events[-1][1]['success'] is (outcome in ('success','finish_failure'))


def test_public_hair_prewrite_verified_receipt_finishes_without_poisoning_attachment(tmp_path, monkeypatch):
    from vroid_mcp import server
    instances, events = [], []
    class FakeRuntime:
        def __init__(self, lab):
            self.mode = 'attached'; self.uncertain = False; instances.append(self)
        def start(self): pass
        async def initialize(self, *a): pass
        async def _call(self, name, args):
            events.append((name, args))
            return {'id': 'receipt'} if name == 'attached_edit_begin' else {'needs_review': False}
        async def scale_brush_hair(self, *a):
            return {'ok': False, 'uncertain': False, 'native_invocation_attempted': False,
                    'dispatch_state': 'prewrite_rejected', 'attached_prewrite_verified': True}
    monkeypatch.setattr(server, 'Runtime', FakeRuntime)
    mcp = server.create_server(tmp_path, 'F00')
    result = asyncio.run(mcp._tool_manager.get_tool('scale_brush_hair').fn(
        expected_model='live', category='HairFront', scope='missing', factor=2))
    assert result['ok'] is False and not instances[0].uncertain
    assert events[-1][1]['success'] is True


@pytest.mark.parametrize('mode', ['copy', 'attached'])
@pytest.mark.parametrize('uncertain_outcome', ['response_lost', 'response_lost_before_dispatch', 'receipt_write_lost'])
def test_public_preview_dynamic_receipts_allow_reads_and_corrected_names(tmp_path, monkeypatch, mode, uncertain_outcome):
    from vroid_mcp import server
    from vroid_mcp.runtime_preview import PreviewTools
    events, instances = [], []
    class FakeRuntime(PreviewTools):
        def __init__(self, lab):
            self.mode = mode; self.uncertain = False; self.lock = asyncio.Lock(); self.pending = None
            self.blocked = False; self.weight = 10; self.setters = 0
            instances.append(self)
        def start(self): pass
        async def initialize(self, *a): pass
        async def _settle(self, *a): return {'model_token': 'live'}
        async def _call(self, name, args):
            events.append((name, args))
            if name == 'attached_edit_begin':
                assert self.pending is None
                self.pending = {'id': 'receipt', 'dispatches': 0}
                return self.pending
            if name == 'attached_edit_finish':
                if args['success'] or not self.pending['dispatches'] and not args['uncertain']:
                    self.pending = None
                return {'needs_review': self.pending is not None}
            if name in ('get_editor_camera', 'list_face_preview'):
                return {'model_token': 'live', 'rotating': False}
            if args.get('name') == 'ile':
                return {'model_token': 'live', 'ok': False, 'uncertain': False,
                        'native_invocation_attempted': False, 'dispatch_state': 'prewrite_rejected'}
            if self.blocked:
                return {'model_token': 'live', 'ok': False, 'uncertain': False,
                        'native_invocation_attempted': False, 'guard_state': 'prewrite_rejected',
                        'dispatch_state': 'prewrite_rejected', 'error': 'ATTACHED_UI_BLOCKED'}
            if args.get('name') == 'late' and uncertain_outcome == 'response_lost_before_dispatch':
                raise RuntimeError('NATIVE_RESPONSE_LOST')
            if self.pending:
                self.pending['dispatches'] += 1
            if args.get('name') == 'late':
                if uncertain_outcome == 'response_lost':
                    raise RuntimeError('NATIVE_RESPONSE_LOST')
                return {'model_token': 'live', 'ok': False, 'uncertain': True,
                        'native_invocation_attempted': False, 'dispatch_state': 'guard_bookkeeping_unconfirmed'}
            self.weight = args['weight']; self.setters += 1
            return {'model_token': 'live', 'ok': True}
    monkeypatch.setattr(server, 'Runtime', FakeRuntime)
    mcp = server.create_server(tmp_path, 'F00')
    camera = mcp._tool_manager.get_tool('editor_camera').fn
    face = mcp._tool_manager.get_tool('face_preview').fn
    asyncio.run(camera(expected_model='live'))
    asyncio.run(face(expected_model='live'))
    assert all(not name.startswith('attached_') for name, args in events)
    assert asyncio.run(face(expected_model='live', name='ile'))['ok'] is False
    assert not instances[0].uncertain and instances[0].pending is None
    assert asyncio.run(face(expected_model='live', name='Smile', weight=60))['ok'] is True
    assert not instances[0].uncertain and instances[0].pending is None
    if mode == 'attached':
        instances[0].blocked = True
        assert asyncio.run(face(expected_model='live', name='Smile', weight=40))['uncertain'] is False
        assert instances[0].weight == 60 and instances[0].setters == 1
        assert not instances[0].uncertain and instances[0].pending is None
        instances[0].blocked = False
        assert asyncio.run(face(expected_model='live', name='Smile', weight=40))['ok'] is True
        assert instances[0].weight == 40 and instances[0].setters == 2
    if uncertain_outcome.startswith('response_lost'):
        with pytest.raises(RuntimeError, match='NATIVE_RESPONSE_LOST'):
            asyncio.run(face(expected_model='live', name='late'))
    else:
        assert asyncio.run(face(expected_model='live', name='late'))['uncertain'] is True
    assert instances[0].uncertain
    assert (instances[0].pending is not None) == (mode == 'attached')
