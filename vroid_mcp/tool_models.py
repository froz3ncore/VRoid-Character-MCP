"""Shared value types for tool inputs.

Kept apart from the tool modules so a domain module only imports the types its
signatures need.

These classes deliberately carry no docstring: a model docstring becomes
``$defs.<Model>.description`` in the published tool schema, and the schema is a
contract this rewrite must not change. The explanations are comments instead.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# One slider write: a native parameter id and its new value.
class FaceChange(BaseModel):
    id: str
    value: float = Field(strict=True, allow_inf_nan=False)


# One typed parameter write; the value shape follows the type listed for that id.
class ParameterChange(BaseModel):
    id: str
    value: bool | float | str | list[float] | list[list[float]]


# One hair colour element write as normalized RGBA.
class HairColorChange(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    color: list[float] = Field(min_length=4, max_length=4)
