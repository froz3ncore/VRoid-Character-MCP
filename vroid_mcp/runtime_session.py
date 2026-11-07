"""Identity-checked, same-process session transitions."""
import asyncio
import ctypes
import os
import time
import zipfile
from ctypes import wintypes

from . import attached_ui
from .bridge import NativeCallNotSent
from .exception_notes import add_exception_note
from .file_paths import file_input
from .custom_item_file import pinned_application


class ExitWatch:
    """Hold a SYNCHRONIZE-only handle. Waiting cannot kill or follow a reused PID."""
    def __init__(self, pid):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.OpenProcess(0x00100000, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def exited(self):
        result = self.api.WaitForSingleObject(self.handle, 0)
        if result not in (0, 258):
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 0

    def close(self):
        if not self.api.CloseHandle(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())


def verified_window(pid):
    state = attached_ui.window_state(pid)
    windows = state.get('windows', [])
    if len(windows) != 1 or state['blocked'] or windows[0]['active_popup'] != windows[0]['window']:
        raise ValueError('SESSION_WINDOW_BLOCKED_OR_CHANGED')
    return hex(windows[0]['window'])


UNKNOWN_MODEL_FIELDS = dict.fromkeys(('active_screen', 'edit_root_active', 'model_open', 'file_path', 'dirty',
                                      'model_type', 'model_variant', 'is_editing', 'can_undo', 'can_redo', 'menu_token'))
DEADLINE = 30


class SessionTools:
    async def session_transition(self, operation, args):
        async with self.lock:
            if self.dead or self.uncertain or getattr(self, 'exit_watch', None):
                raise RuntimeError('SESSION_UNAVAILABLE: inspect status before another transition')
            if self.mode == 'copy' and not self.owns_process:
                raise ValueError('SESSION_OWNER_REQUIRED')
            if operation in ('create_from_menu', 'open_from_menu'):
                if not args.get('expected_menu'):
                    raise ValueError('EXPECTED_MENU_REQUIRED')
                if self.mode == 'attached' and args.get('confirm_attached') is not True:
                    raise ValueError('CONFIRM_ATTACHED_REQUIRED')
            elif not args.get('expected_model'):
                raise ValueError('EXPECTED_MODEL_REQUIRED')
            if operation == 'exit_vroid' and self.mode == 'attached' and args.get('close_attached') is not True:
                raise ValueError('CLOSE_ATTACHED_REQUIRED')
            args = dict(args, operation=operation, window=verified_window(self.pid))
            if operation == 'open_from_menu':
                path = file_input(self.lab, args.pop('filename'), ('.vroid',), self.mode == 'attached')
                with pinned_application(self, path):
                    with zipfile.ZipFile(path) as archive:
                        if not archive.namelist() or archive.testzip() is not None:
                            raise ValueError('Invalid VRoid archive')
                    return await self._dispatch_session(operation, dict(args, path=str(path)))
            return await self._dispatch_session(operation, args)

    async def _dispatch_session(self, operation, args):
        watch = ExitWatch(self.pid) if operation == 'exit_vroid' else None
        receipt = None
        try:
            if watch and watch.exited():
                raise RuntimeError('SESSION_PROCESS_ALREADY_EXITED')
            await self._call('get_session_preflight', args)
            if self.mode == 'attached':
                receipt = await self._call('attached_edit_begin', {'tool':operation})
                args['receipt_id'] = receipt['id']
        except BaseException:
            if watch:
                watch.close()
            raise
        if watch:
            self.exit_watch = watch
        refusal = None
        try:
            try:
                dispatched = await self._call(operation, args)
                if dispatched.get('rejected'):
                    refusal = ValueError(dispatched['error'])
            except NativeCallNotSent as error:
                refusal = error
            except Exception:
                if not watch:
                    raise
                # Native exit may sever Frida before its RPC response. The handle
                # remains authoritative for the entire remaining observation.
                dispatched = {}
            if refusal is not None:
                if watch:
                    self.exit_watch = None
                    watch.close()
                if receipt:
                    try:
                        await self._finish_session_receipt(receipt, success=False)
                    except Exception as cleanup:
                        # The mutation was refused. A separate unfinished receipt
                        # remains inspectable through the standard review/ack path.
                        add_exception_note(refusal, 'Inspect get_attached_state after the dialog closes; '
                                           'session receipt cleanup failed: ' + str(cleanup))
            elif watch:
                await self._await_exit(watch)
                return {'stopped': True, 'pid': self.pid, 'mode': self.mode, 'graceful': True}
            else:
                result = await self._await_session(operation, args, dispatched)
                if receipt:
                    await self._finish_session_receipt(receipt)
                return result
        except BaseException:
            self.uncertain = True
            raise
        raise refusal

    async def _finish_session_receipt(self, receipt, success=True):
        try:
            done = await self._call('attached_edit_finish', {'id':receipt['id'], 'success':success, 'uncertain':False})
            if done['needs_review']:
                raise RuntimeError('ATTACHED_EDIT_NEEDS_REVIEW')
        except BaseException:
            self.uncertain = True
            raise

    async def _await_exit(self, watch):
        deadline = time.monotonic() + DEADLINE
        while not watch.exited():
            if time.monotonic() >= deadline:
                raise TimeoutError('GRACEFUL_EXIT_PENDING: inspect status; never retry quit')
            await asyncio.sleep(.1)
        closed = self.close()
        if not closed.get('native_process_stopped'):
            raise RuntimeError('GRACEFUL_EXIT_CLEANUP_PENDING: ' + str(closed))

    async def _await_session(self, op, args, dispatched):
        if op == 'open_from_menu':
            await self._task(dispatched)
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            status = await self._call('status')
            if op == 'return_to_main_menu':
                if (status.get('menu_token') and status.get('model_open') is False
                        and not status.get('model_ready') and status.get('active_screen') == 'VRoid.Studio.StartScreen.ViewModel'):
                    return status
            elif status.get('model_ready') and status.get('edit_root_active') is True:
                settled = await self._settle()
                if (settled.get('edit_root_active') is not True or not settled.get('model_token')
                        or settled['model_token'] != status.get('model_token')):
                    raise RuntimeError('SESSION_MODEL_OWNER_CHANGED')
                if op == 'create_from_menu' and settled.get('model_variant') != args['variant']:
                    raise RuntimeError('SESSION_TEMPLATE_UNCONFIRMED')
                if op == 'open_from_menu' and os.path.normcase(settled.get('file_path') or '') != os.path.normcase(args['path']):
                    raise RuntimeError('SESSION_OPEN_PATH_UNCONFIRMED')
                return settled
            await asyncio.sleep(.1)
        raise TimeoutError('SESSION_TRANSITION_PENDING: do not retry')
