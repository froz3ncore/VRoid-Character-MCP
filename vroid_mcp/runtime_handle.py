"""Indirection between the tool modules and the live native runtime.

`restart_session` replaces the Runtime object. Tool modules are registered once,
so they must not capture the object they were given at registration time: they
hold this handle and always reach whichever runtime is current.

The handle forwards attribute access, so a tool body reads the same as before
(`runtime.wear_status()`), while the restart path rebinds it in one place.
"""

from __future__ import annotations

from typing import Any


class RuntimeHandle:
    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def rebind(self, runtime: Any) -> None:
        self._runtime = runtime

    @property
    def current(self) -> Any:
        return self._runtime

    def __getattr__(self, name: str) -> Any:
        # Only reached for names this class does not define, which is exactly
        # the runtime API the tools use.
        return getattr(self._runtime, name)
