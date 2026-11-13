"""Offline topic help and MCP resources share the published FastMCP registry."""
from pathlib import Path
import sysconfig


GUIDES = {
    'overview': (
        'Use get_status to inspect the active model and toolset. Pass its model_token as expected_model.',
        '用 get_status 查看当前模型和工具版本。将 model_token 作为 expected_model 传给编辑工具。'),
    'session': (
        'Save first. return_to_main_menu accepts the current model token. When menu_ready is true, use its menu_token with create_from_menu or open_from_menu. A fresh profile can show InitialAgreements instead; finish its initial setup in VRoid before requesting another status. exit_vroid waits for graceful exit. restart_session explicitly starts a new copy.',
        '先保存模型。return_to_main_menu 接收当前模型令牌；menu_ready 为真时，才能用 menu_token 新建或打开模型。新配置可能进入首次协议页面，请在 VRoid 完成初始设置后重新查看状态。exit_vroid 等待进程退出，restart_session 可显式启动新副本。'),
    'batch': (
        'run_batch executes ordered calls without rollback. Read each result and stopped_at before continuing. Never replay an uncertain edit.',
        'run_batch 按顺序执行且不回滚。检查每项结果与 stopped_at，遇到不确定状态时先检查模型，避免重复执行。'),
    'migration': (
        'The migration matrix maps source capabilities to target contracts and records native verification limits.',
        '迁移对照表列出来源工具、目标能力和实机验收范围。离线测试无法确认原生编辑、导出或外观。'),
}


def register(mcp, read):
    @mcp.tool(annotations=read)
    async def get_help(topic: str = 'overview', language: str = 'en') -> dict:
        """Read offline overview/session/batch/migration/tools or a registered tool's exact input schema."""
        requested = language.lower().replace('_', '-')
        lang = 'zh' if requested.split('-')[0] == 'zh' else 'en'
        out = {'topic': topic, 'language': lang, 'requested_language': language,
               'fallback': requested.split('-')[0] not in {'en', 'zh'}}
        if topic in GUIDES:
            out['guide'] = GUIDES[topic][lang == 'zh']
            out['topics'] = [*GUIDES, 'tools']
            if topic == 'migration':
                matrix = Path(__file__).resolve().parents[1] / 'MIGRATION.md'
                if not matrix.is_file():
                    matrix = Path(sysconfig.get_path('data')) / 'share/vroid-character-mcp/MIGRATION.md'
                out['matrix'] = matrix.read_text(encoding='utf-8')
        elif topic == 'tools':
            out['tools'] = [tool.name for tool in await mcp.list_tools()]
        else:
            tool = mcp._tool_manager.get_tool(topic)
            if tool is None:
                raise ValueError('UNKNOWN_HELP_TOPIC: ' + topic)
            out.update(description=tool.description, inputSchema=tool.parameters)
        return out

    def resource(topic, language):
        async def content() -> dict:
            return await get_help(topic, language)
        mcp.resource(f'vroid://help/{language}/{topic}', name=f'{topic} ({language})',
                     mime_type='application/json')(content)

    for topic in (*GUIDES, 'tools'):
        for language in ('en', 'zh'):
            resource(topic, language)
