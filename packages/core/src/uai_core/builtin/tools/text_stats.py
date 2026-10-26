"""Treat all input as text data. No eval, filesystem, network or model access."""
from pydantic import BaseModel, ConfigDict, Field

from ...tools import ToolDefinition


class TextStatsInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(max_length=32000)


class TextStatsOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    characters: int = Field(ge=0)
    words: int = Field(ge=0)
    lines: int = Field(ge=0)


async def text_stats(params: TextStatsInput) -> TextStatsOutput:
    return TextStatsOutput(characters=len(params.text), words=len(params.text.split()),
                           lines=len(params.text.splitlines()))


def definition() -> ToolDefinition:
    return ToolDefinition(id='builtin.text_stats', name='Text statistics',
                          description='Count Unicode characters, whitespace-delimited words and splitlines in supplied text.',
                          version='1.0.0', input_schema=TextStatsInput.model_json_schema(),
                          output_schema=TextStatsOutput.model_json_schema(), permissions={'tools:execute'},
                          risk_level='read_only', timeout=1)
