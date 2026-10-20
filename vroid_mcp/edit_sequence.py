"""Conservative session guard for the validated build's body/texture crash.

A confirmed body edit requires a cold reopen before entering texture editing.
Undo is not proof that the native overlay cache was reconstructed. This gate
does not claim to detect manual edits made outside this MCP session.
"""
REOPEN_REQUIRED = (
    'TEXTURE_EDITOR_REOPEN_REQUIRED: body parameters changed in this model session. '
    'This VRoid build can crash when entering texture editing afterwards. '
    'Save to a new .vroid first, close this session normally, and start a new '
    'session with that saved model. Do makeup before body edits when possible. '
    'Nothing entered the texture editor; do not restart with unsaved work.'
)


def before_call(subject, operation: str, args: dict) -> None:
    if operation == 'open_texture_editor' and args.get('expected_model') in getattr(
            subject, 'body_edited_tokens', set()):
        raise RuntimeError(REOPEN_REQUIRED)


def after_call(subject, operation: str, args: dict, result) -> None:
    body_edit = operation == 'set_body_params' or (
        operation == 'set_parameters' and args.get('domain') == 'body')
    if not body_edit or not isinstance(result, dict):
        return
    changed = any(row.get('before') != row.get('after') for row in result.get('applied', []))
    if changed:
        token = result.get('model_token') or args.get('expected_model')
        if token:
            if not hasattr(subject, 'body_edited_tokens'):
                subject.body_edited_tokens = set()
            subject.body_edited_tokens.add(token)


def status(subject, token: str | None) -> dict:
    blocked = token in getattr(subject, 'body_edited_tokens', set())
    return {'requires_cold_reopen': blocked,
            'reason': 'BODY_EDIT_IN_THIS_SESSION' if blocked else None,
            'scope': 'MCP-observed body edits only; other tools remain available. '
                     'Cold reopen is required before entering texture editing.'}
