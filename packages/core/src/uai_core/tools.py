"""Public-safe tool metadata; executable callables belong to a trusted host registry."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, model_validator

ToolID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.-]{0,99}$')]
Permission = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]*:[a-z][a-z0-9_-]*$', max_length=100)]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    id: ToolID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=4000)
    version: str = Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$', max_length=50)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    permissions: frozenset[Permission] = Field(min_length=1, max_length=32)
    risk_level: Literal['read_only', 'write', 'destructive']
    timeout: float = Field(default=5, gt=0, le=120)
    retry_policy: Literal['never'] = 'never'
    executor: Literal['builtin', 'http', 'mcp', 'isolated'] = 'builtin'

    @field_serializer('permissions')
    def serialize_permissions(self, value):
        return sorted(value)

    @model_validator(mode='after')
    def bound_metadata(self):
        if not self.input_schema or not self.output_schema or len(self.model_dump_json().encode()) > 8192:
            raise ValueError('tool_metadata_limit')
        return self


class ToolExecutionError(Exception):
    """Normalized code only, never arguments, output or executor diagnostics."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
