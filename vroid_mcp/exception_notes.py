"""Retain cleanup diagnostics on the primary exception on Python 3.10+."""


def add_exception_note(error: BaseException, note: str) -> None:
    add_note = getattr(error, 'add_note', None)
    if callable(add_note):
        add_note(note)
    else:
        if not hasattr(error, '__notes__'):
            error.__notes__ = []
        error.__notes__.append(note)
