"""Fallback guards for sessions without the validated native PNG decoder.

Managed copies with the decoder can edit continuously. Unverified sessions keep
the earlier conservative boundaries; manual history in attached windows is unknown.
"""
REOPEN_REQUIRED = (
    'TEXTURE_EDITOR_REOPEN_REQUIRED: body parameters changed in this model session. '
    'This session has no verified native PNG lifetime fix for continuous editing. '
    'Save to a new .vroid first, close this session normally, and start a new '
    'session with that saved model. Do makeup before body edits when possible. '
    'Nothing entered the texture editor; do not restart with unsaved work.'
)

WEAR_RESTART_REQUIRED = (
    'WEAR_NEW_PROCESS_REQUIRED: texture editing was entered in this process. '
    'This session has no verified native PNG lifetime fix for entering Dress-up. '
    'Close the texture editor and save to a new .vroid if needed, then close '
    'this session normally and open the saved file in Dress-up from a fresh '
    'session. Nothing entered Dress-up; unsaved work was not discarded.'
)


def decoder_enabled(subject) -> bool:
    return bool(getattr(subject, 'native_png_decoder_ready', False))


def before_call(subject, operation: str, args: dict) -> None:
    if decoder_enabled(subject):
        return
    if operation == 'open_wear_project' and getattr(subject, 'texture_editor_entered', False):
        raise RuntimeError(WEAR_RESTART_REQUIRED)
    if operation == 'open_texture_editor' and args.get('expected_model') in getattr(
            subject, 'body_edited_tokens', set()):
        raise RuntimeError(REOPEN_REQUIRED)


def after_call(subject, operation: str, args: dict, result) -> None:
    if (operation == 'open_texture_editor' and isinstance(result, dict)
            and result.get('active_screen') == 'VRoid.Studio.TextureEditorScreen.ViewModel'):
        # Closing the editor or loading another model is not evidence that its
        # process-wide native objects were reconstructed. Clear only on restart.
        subject.texture_editor_entered = True
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
    if decoder_enabled(subject):
        return {'requires_cold_reopen': False, 'reason': None,
                'scope': 'Verified native synchronous PNG decode with deferred callbacks.'}
    blocked = token in getattr(subject, 'body_edited_tokens', set())
    return {'requires_cold_reopen': blocked,
            'reason': 'BODY_EDIT_IN_THIS_SESSION' if blocked else None,
            'scope': 'MCP-observed body edits only. '
                     'Cold reopen is required before entering texture editing.'}


def wear_status(subject) -> dict:
    if decoder_enabled(subject):
        return {'requires_new_process': False, 'reason': None,
                'scope': 'Verified native synchronous PNG decode with deferred callbacks.'}
    blocked = getattr(subject, 'texture_editor_entered', False)
    return {'requires_new_process': blocked,
            'reason': 'TEXTURE_EDITOR_ENTERED_IN_THIS_PROCESS' if blocked else None,
            'scope': 'Conservative workaround for an unresolved native transition crash; '
                     'MCP-observed texture entry only. Saving and reading remain available.'}
