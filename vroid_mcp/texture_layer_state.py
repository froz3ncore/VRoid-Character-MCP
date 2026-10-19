"""Optimistic native layer-state edits; pixel content and other layers stay untouched."""
import hashlib,json,math
from pydantic import Field,StrictBool

STATE_FIELDS=('layer_id','Name','Opacity','Visibility','CompositionMode','AlphaLocked')
def metadata(layer):return {key:layer.get(key) for key in STATE_FIELDS}
def state_digest(layer):return hashlib.sha256(json.dumps(metadata(layer),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def describe_layers(result):
    for layer in result['layers']:layer['state_sha256']=state_digest(layer)
    return result

def register_layer_state_tools(ready_tool,runtime,read,edit):
    @ready_tool(annotations=edit)
    async def set_texture_layer_state(expected_model: str,region_id: str,layer_id: str,expected_state_sha256: str = Field(pattern=r'^[0-9a-f]{64}$'),visible: StrictBool | None = None,opacity: float | None = Field(default=None,ge=0,le=1,allow_inf_nan=False,strict=True)) -> dict:
        """Change an EXISTING raster layer's visibility/opacity in its matching open native canvas. Pass state_sha256 from a fresh list_texture_layers result; stale metadata is rejected again on the native write boundary. Preserves PNG pixels, other layers and order. Native history supports Undo/Redo; no-op returns zero commands. Does not save or retry partial native errors."""
        if visible is None and opacity is None:raise ValueError('Specify visibility and/or opacity')
        if visible is not None and type(visible) is not bool:raise ValueError('Visibility must be boolean')
        if opacity is not None and (type(opacity) not in (int,float) or not math.isfinite(opacity) or not 0<=opacity<=1):raise ValueError('Opacity must be finite within 0..1')
        result=await runtime.parameter_call('list_texture_layers',{'expected_model':expected_model,'region_id':region_id})
        rows=[row for row in result['layers'] if row['layer_id']==layer_id]
        if len(rows)!=1 or state_digest(rows[0])!=expected_state_sha256:raise ValueError('Layer metadata changed or layer is missing; relist before editing')
        result=await runtime.parameter_call('set_texture_layer_state',{'expected_model':expected_model,'region_id':region_id,'layer_id':layer_id,'expected_layer':metadata(rows[0]),'visible':visible,'opacity':opacity},True)
        result['layer']['state_sha256']=state_digest(result['layer']);result['saved']=False;return result
