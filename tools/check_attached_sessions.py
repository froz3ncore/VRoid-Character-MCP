"""Reproduce attachment lifecycle checks using a new, test-owned VRoid fixture.

Requires --source (supported installation, read only) and a NEW --out directory.
The fixture has its own startup profile guard; the attached MCP agent does not.
This is controlled native evidence, not independent acceptance on a user's profile.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from pathlib import Path
import sys
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import prepare_lab
from vroid_mcp import bridge
from vroid_mcp.runtime import Runtime


async def check(source: Path, out: Path, variant: str = 'F00') -> dict:
    if out.exists():
        raise FileExistsError('Use a NEW output directory; existing fixtures are never replaced')
    source, out = source.resolve(), out.resolve()
    # Check separation before creating out or copying anything.
    prepare_lab.check_directories(source, out)
    prepare_lab.check_install(source)
    out.mkdir(parents=True)
    scratch = out / 'temp'
    scratch.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(scratch)
    target = out / 'target'
    await asyncio.to_thread(prepare_lab.main, ['--source', str(source), '--lab', str(target)])
    fixture = Runtime(target)
    fixture.run_dir.mkdir(parents=True)
    dev = frida.get_local_device()
    pid = None
    guard_session = None
    controller = None
    observer = None
    crashed_server = None
    report = {'scope': 'test-owned external fixture with isolated startup profile',
              'variant': variant, 'checks': {}}

    def passed(name, evidence=True):
        report['checks'][name] = evidence
        print('PASS ' + name, flush=True)

    def alive():
        return any(p.pid == pid for p in dev.enumerate_processes())

    async def observe():
        """Read background policy on the Unity thread without adopting/enabling it."""
        nonlocal observer
        if observer is None:
            observer = Runtime(out / 'observer')
            original = bridge.script_text
            def instrument(*args, **kwargs):
                return original(*args, **kwargs) + "\nrpc.exports.observe = () => schedule(() => ({background: nativeClass('UnityEngine.CoreModule','UnityEngine.Application').method('get_runInBackground').invoke()}), true);"
            bridge.script_text = instrument
            try:
                await asyncio.to_thread(observer.attach, pid)
            finally:
                bridge.script_text = original
            deadline = asyncio.get_running_loop().time() + 30
            while not (await asyncio.to_thread(observer.script.exports_sync.health))['ready']:
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError('Observer not ready')
                await asyncio.sleep(.1)
        # Keep observation independent of the MCP host's attach/release cycles.
        # The observer never adopts a background lease or edits the model.
        return await asyncio.to_thread(observer.script.exports_sync.observe)

    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'vroid_mcp.server', '--lab', str(out / 'client')],
        cwd=str(ROOT), env=dict(os.environ))
    try:
        pid = dev.spawn([str(fixture.exe), '-logFile', str(fixture.run_dir / 'Player.log'),
                         '-screen-fullscreen', '0', '-screen-width', '960', '-screen-height', '720'],
                        cwd=str(fixture.exe.parent), env=bridge._environment(fixture), stdio='pipe')
        guard_session = dev.attach(pid)
        guard_code = ('const PROBE=' + json.dumps(bridge._probe_config(fixture)) + ';\n' +
                      (ROOT / 'agent/native_traps.js').read_text(encoding='utf8') + '\n' +
                      (ROOT / 'agent/profile_guard.js').read_text(encoding='utf8'))
        guard = guard_session.create_script(guard_code)
        guard.load()
        dev.resume(pid)
        await asyncio.sleep(10)
        baseline = await observe()
        passed('background_observed_before_attach', baseline)
        with (out / 'server.log').open('w', encoding='utf8') as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=90)) as client:
                    await client.initialize()
                    async def call(name, args=None, error=None):
                        response = await client.call_tool(name, args or {})
                        if error:
                            assert response.isError and error in str(response.content), response
                            return {'refused': error}
                        if response.isError:
                            raise RuntimeError(name + ': ' + str(response.content))
                        return response.structuredContent or json.loads(response.content[0].text)

                    initial = await call('attach_open_vroid', {'pid': pid})
                    assert initial['connected'] and not initial['model_ready']
                    passed('attach_at_home_without_model')
                    # Simulate the user creating a model through a second test-owned controller.
                    controller = Runtime(out / 'controller')
                    original_script = bridge.script_text
                    def fixture_script(*args, **kwargs):
                        return original_script(*args, **kwargs) + "\nrpc.exports.fixturemodel = variant => schedule(() => {const type = nativeClass('VRoid.Studio','VRoid.Studio.MainViewModel'); const main = Il2Cpp.gc.choose(type).filter(o => o.class.handle.equals(type.handle)); if(main.length!==1)throw Error('FIXTURE_MAIN_NOT_UNIQUE'); rememberSingleton('VRoid.Studio.MainViewModel', main[0]); return vroid.dispatch('new_model',{variant});},true);"
                    bridge.script_text = fixture_script
                    try:
                        await asyncio.to_thread(controller.attach, pid)
                    finally:
                        bridge.script_text = original_script
                    await asyncio.to_thread(controller.script.exports_sync.fixturemodel, variant)
                    await controller._settle()
                    await asyncio.to_thread(controller.close)
                    face = await call('list_face_params')
                    token = face['model_token']
                    original_value = next(p['value'] for p in face['parameters'] if p['id'] == 'face/FaceSet/006')
                    assert token
                    passed('model_created_after_attach_is_discovered')
                    again = await call('attach_open_vroid', {'pid': pid})
                    assert again['model_token'] == token
                    passed('same_pid_attach_is_idempotent')
                    await call('set_face_params', {'expected_model': token,
                                                  'changes': [{'id': 'face/FaceSet/006', 'value': .5}]})
                    await call('undo', {'expected_model': token})
                    undone = await call('list_face_params')
                    assert abs(next(p['value'] for p in undone['parameters'] if p['id'] == 'face/FaceSet/006') - original_value) < 1e-6
                    await call('redo', {'expected_model': token})
                    redone = await call('list_face_params')
                    assert abs(next(p['value'] for p in redone['parameters'] if p['id'] == 'face/FaceSet/006') - .5) < 1e-6
                    passed('native_undo_redo_preserves_history')
                    for name, args in [('open_texture_editor', {'expected_model': token, 'region_id': 'unused'}),
                                       ('save_custom_items', {'expected_model': token, 'types': ['Iris']})]:
                        await call(name, args, error='ATTACHED_')
                    passed('unsafe_attached_operations_refused')
                    detached = await call('detach_open_vroid')
                    assert detached['release']['background_restored'] and alive()
                    passed('detach_preserves_process')
                    restored = await observe()
                    assert restored == baseline, (restored, baseline)
                    passed('background_policy_really_restored', restored)
                    second = await call('attach_open_vroid', {'pid': pid})
                    assert second['model_token'] != token
                    await call('set_face_params', {'expected_model': token,
                               'changes': [{'id': 'face/FaceSet/006', 'value': .9}]}, error='STALE_MODEL')
                    face = await call('list_face_params')
                    assert abs(next(p['value'] for p in face['parameters'] if p['id'] == 'face/FaceSet/006') - .5) < 1e-6
                    passed('reattach_preserves_unsaved_edit_and_rejects_old_token')
                    # Leave attached: normal client EOF must run the server lifespan cleanup.
            assert alive()
            passed('client_eof_preserves_target')
            restored = await observe()
            assert restored == baseline
            passed('client_eof_restores_background', restored)
        # Kill an actual MCP host process without EOF or lifespan cleanup.
        with (out / 'forced-exit-server.log').open('w', encoding='utf8') as log:
            crashed_server = await asyncio.create_subprocess_exec(sys.executable, '-m', 'vroid_mcp.server',
                '--lab', str(out / 'client'), cwd=str(ROOT), env=dict(os.environ),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log)
            request_id = 0
            async def rpc(method, arguments):
                nonlocal request_id
                request_id += 1
                crashed_server.stdin.write((json.dumps({'jsonrpc':'2.0', 'id':request_id,
                    'method':method, 'params':arguments}) + '\n').encode())
                await crashed_server.stdin.drain()
                while True:
                    line = await asyncio.wait_for(crashed_server.stdout.readline(), 90)
                    if not line:
                        raise RuntimeError('Crash-test MCP host exited before response')
                    response = json.loads(line)
                    if response.get('id') == request_id:
                        if 'error' in response or response.get('result', {}).get('isError'):
                            raise RuntimeError(str(response))
                        return response['result']
            await rpc('initialize', {'protocolVersion':'2024-11-05', 'capabilities':{},
                'clientInfo':{'name':'forced-exit-check','version':'1'}})
            crashed_server.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await crashed_server.stdin.drain()
            attached_reply = await rpc('tools/call', {'name':'attach_open_vroid','arguments':{'pid':pid}})
            attached = attached_reply.get('structuredContent') or json.loads(attached_reply['content'][0]['text'])
            host_pid = attached['adopted']['owner_pid']
            assert host_pid > 0 and host_pid not in (os.getpid(), pid)
            competitor = StdioServerParameters(command=sys.executable,
                args=['-m', 'vroid_mcp.server', '--lab', str(out / 'competing-client')],
                cwd=str(ROOT), env=dict(os.environ))
            with (out / 'competing-server.log').open('w', encoding='utf8') as competing_log:
                async with stdio_client(competitor, errlog=competing_log) as (reader, writer):
                    async with ClientSession(reader, writer) as competing_client:
                        await competing_client.initialize()
                        refused = await competing_client.call_tool('attach_open_vroid', {'pid':pid})
                        assert refused.isError and 'ATTACHMENT_ALREADY_OWNED' in str(refused.content), refused
            passed('second_live_host_refused_without_stealing_connection')
            report['forced_host_pid'] = host_pid
            report['launcher_pid'] = crashed_server.pid
            # Windows os.kill(SIGTERM) uses TerminateProcess. Kill the actual
            # Python host, which may be a child of the virtualenv launcher.
            os.kill(host_pid, signal.SIGTERM)
            await asyncio.wait_for(crashed_server.wait(), 15)
            assert alive()
            passed('forced_host_exit_preserves_target')
            after_crash = await observe()
            report['background_immediately_after_forced_exit'] = after_crash
        # A fresh server must reacquire the client lock and attach to the same unsaved model.
        with (out / 'recovery-server.log').open('w', encoding='utf8') as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=90)) as client:
                    await client.initialize()
                    async def recover(name, args=None):
                        response = await client.call_tool(name, args or {})
                        if response.isError:
                            raise RuntimeError(str(response.content))
                        return response.structuredContent or json.loads(response.content[0].text)
                    attachment = await recover('attach_open_vroid', {'pid': pid})
                    assert attachment['adopted']['recovered_previous_host']
                    passed('new_host_recovers_previous_host_lease')
                    face = await recover('list_face_params')
                    assert abs(next(p['value'] for p in face['parameters'] if p['id'] == 'face/FaceSet/006') - .5) < 1e-6
                    passed('new_client_reattaches_after_forced_exit')
                    restarted = await recover('restart_session')
                    assert restarted['detached'] and alive()
                    passed('attached_restart_only_detaches')
                    restored = await observe()
                    assert restored == baseline, (restored, baseline)
                    passed('reattach_after_forced_exit_restores_background', restored)
                    await recover('attach_open_vroid', {'pid': pid})
                    dev.kill(pid)  # exclusively the process spawned above
                    await asyncio.sleep(.5)
                    status = await recover('get_status')
                    assert not status['connected'] and status['reason'] == 'ATTACHED_VROID_DISCONNECTED'
                    passed('target_exit_reports_disconnected')
                    await recover('detach_open_vroid')
        report['passed'] = True
    except BaseException as error:
        report.update(passed=False, error=repr(error))
        raise
    finally:
        if crashed_server is not None and crashed_server.returncode is None:
            crashed_server.kill()
            await crashed_server.wait()
        if controller is not None and not controller.dead:
            await asyncio.to_thread(controller.close)
        if pid is not None:
            try:
                dev.kill(pid)
            except frida.ProcessNotFoundError:
                pass
        if guard_session:
            try:
                guard_session.detach()
            except frida.InvalidOperationError:
                pass
        if observer is not None:
            await asyncio.to_thread(observer.close)
        (out / 'checks.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--variant', choices=['F00', 'M00'], default='F00')
    args = parser.parse_args()
    asyncio.run(check(args.source, args.out, args.variant))


if __name__ == '__main__':
    main()
