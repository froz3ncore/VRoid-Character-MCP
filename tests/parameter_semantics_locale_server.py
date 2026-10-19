"""Test-only English message table; the public MCP catalog stays unchanged."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vroid_mcp import server
from vroid_mcp.runtime import Runtime,PROJECT


class EnglishRuntime(Runtime):
    def start(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            source=original(path,*args,**kwargs)
            if path==PROJECT/'agent/operations.js':
                marker='const operations={'
                inject="""const operations={test_parameter_language(){
                    const type=Il2Cpp.domain.assemblies.map(a=>a.image.tryClass('VRoid.UI.Messages.Messages')).find(c=>c);
                    if(!type)throw Error('Messages type unavailable');
                    type.method('set_CurrentCrowdinLanguageCode',1).invoke(Il2Cpp.string('en'));
                    return {language:text(type.method('get_CurrentCrowdinLanguageCode',0).invoke())};
                },"""
                if source.count(marker)!=1:raise AssertionError('Locale test injection marker changed')
                source=source.replace(marker,inject)
            return source
        with patch.object(Path,'read_text',read):super().start()

    async def initialize(self,variant='F00',model_file=None):
        await super().initialize(variant,model_file)
        result=await self._call('test_parameter_language')
        if result['language']!='en':raise AssertionError('Test message language not changed')
        if model_file is None:raise ValueError('Locale test requires a saved lab fixture')
        return await self.reopen_for_test(model_file)


server.Runtime=EnglishRuntime
if __name__=='__main__':server.main()
