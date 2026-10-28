"""Detect a disabled Unity owner before submitting work to its frame queue."""
import ctypes
import os
from ctypes import wintypes


def window_state(pid):
    if os.name != 'nt' or not pid:
        return {'blocked': False}
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.IsWindowEnabled.argtypes = [wintypes.HWND]
    user.GetLastActivePopup.argtypes = [wintypes.HWND]
    user.GetLastActivePopup.restype = wintypes.HWND
    rows = []
    def inspect(hwnd, unused):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            name = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, len(name))
            if name.value == 'UnityWndClass':
                popup = user.GetLastActivePopup(hwnd)
                rows.append({'window': int(hwnd), 'enabled': bool(user.IsWindowEnabled(hwnd)),
                             'active_popup': int(popup or 0)})
        return True
    callback = callback_type(inspect)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    if not user.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'blocked': any(not row['enabled'] for row in rows), 'windows': rows}
