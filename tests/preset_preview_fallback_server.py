"""Test-only server forcing the preview path in the owned lab's injected source.

The production file stays unchanged. This exercises the real asynchronous native
preview pipeline even when every built-in asset has a directly readable thumbnail.
"""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime, PROJECT


class FallbackRuntime(Runtime):
    def start(self):
        original=Path.read_text
        target=PROJECT/'agent/preset_previews.js'
        def read(path,*args,**kwargs):
            source=original(path,*args,**kwargs)
            if path==target:
                marker='const texture=direct(entry.resource_name);'
                if source.count(marker)!=1:raise AssertionError('Fallback injection marker changed')
                source=source.replace(marker,'const texture=null; // test-only forced asset-store miss')
            return source
        with patch.object(Path,'read_text',read):
            super().start()


server.Runtime=FallbackRuntime
if __name__=='__main__':server.main()
