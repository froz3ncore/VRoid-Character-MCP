"""The domain surface of one lab, composed from three mixins over the bridge.

`bridge.py` owns the process, the script and the call protocol.
`runtime_edit.py`, `runtime_capture.py` and `runtime_wear.py` add the operations
the tools call. This module holds the state they share and composes them.

State lives on this object rather than on a helper because that is the seam the
tests stub: they build `Runtime.__new__(Runtime)`, install a fake `script` and a
`lock`, and call the domain methods directly. The plumbing functions take the
runtime as their subject, so such a stub still exercises the real call path.

Artifact policy (`review_folder`, `save_destination`, `validate_capture`) is
re-exported here so existing imports keep working.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from . import bridge as frida_bridge
from .bridge import PROJECT
from .lab_paths import review_folder, save_destination, validate_capture
from .runtime_capture import CaptureTools
from .runtime_edit import EditTools
from .runtime_wear import WearTools
from .runtime_ordinary import OrdinaryTools

__all__ = ['Runtime', 'review_folder', 'save_destination', 'validate_capture']


class Runtime(OrdinaryTools, EditTools, CaptureTools, WearTools):
    """One lab: process ownership from the bridge, operations from the mixins."""

    def __init__(self, lab: pathlib.Path, bridge_js: pathlib.Path | None = None) -> None:
        self.lab = lab.resolve()
        self.exe = self.lab / 'app' / 'VRoidStudio.exe'
        self.bridge_js = bridge_js or PROJECT / 'node_modules/frida-il2cpp-bridge/dist/index.js'
        self.pid: int | None = None
        self.mode = 'copy'
        self.owns_process = False
        self.target: str | None = None
        self.device = self.session = self.script = None
        self.lock = asyncio.Lock()
        self.file_lock = None
        self.lab_owner: int | None = None
        self.crash_guard: dict = {}
        self.dead = False
        self.uncertain = False
        self.body_edited_tokens: set[str] = set()
        self.texture_editor_entered = False
        self.native_png_decoder_ready = False
        self.events: list[dict] = []
        self.run_dir = frida_bridge.run_directory(self.lab)

    # The process belongs to bridge.py; these keep the call sites unchanged.
    def start(self) -> None:
        frida_bridge.start(self)

    def attach(self, pid: int) -> None:
        frida_bridge.attach(self, pid)

    async def adopt(self) -> dict:
        return await frida_bridge.adopt(self)

    async def initialize(self, variant: str = 'F00', model_file: pathlib.Path | None = None) -> dict:
        return await frida_bridge.initialize(self, variant, model_file)

    async def _call(self, operation: str, args: dict | None = None) -> Any:
        return await frida_bridge.call(self, operation, args)

    async def _task(self, task: dict) -> None:
        return await frida_bridge.wait_task(self, task)

    async def _settle(self, after_frame: int = -1) -> dict:
        return await frida_bridge.settle(self, after_frame)

    async def status(self) -> dict:
        return await frida_bridge.status(self)

    def close(self) -> dict:
        return frida_bridge.close(self)
