"""Installed trusted example. Exposes a read-only weather tool."""
from pydantic import BaseModel, ConfigDict

from uai_core.models import Message
from uai_plugin_sdk.manifest import PluginManifest
from uai_plugin_sdk.plugin import Plugin, PluginHealth
from uai_core.tools import ToolDefinition


class WeatherConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WeatherInput(BaseModel):
    city: str


class WeatherOutput(BaseModel):
    city: str
    forecast: str


class WeatherPlugin(Plugin):
    def __init__(self):
        super().__init__(PluginManifest(id='org.uai.weatheragent', name='WeatherAgent', version='0.1.0',
            compatibility={'core': '>=0.1.0,<1'}, capabilities={'tools'},
            config_schema=WeatherConfig.model_json_schema()))

    def register(self, registrar):
        async def handler(inp: WeatherInput) -> WeatherOutput:
            return WeatherOutput(city=inp.city, forecast='sunny')

        registrar.add_tool(
            ToolDefinition(name='org.uai.weatheragent.weather', description='Get weather for a city'),
            input_model=WeatherInput, output_model=WeatherOutput, handler=handler,
        )

    async def health(self):
        return PluginHealth(status='ok')