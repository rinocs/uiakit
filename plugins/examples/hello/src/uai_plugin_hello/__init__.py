"""Installed trusted example. The directive runs only when an assistant selects it."""
from pydantic import BaseModel, ConfigDict
from uai_core.directives import Directive
from uai_core.models import Message
from uai_plugin_sdk.manifest import PluginManifest
from uai_plugin_sdk.plugin import Plugin, PluginHealth


class HelloConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Greeting(Directive):
    async def before_model(self, context):
        messages = context.model_input.messages
        last = messages[-1]
        return context.with_messages(messages[:-1] + (Message(role=last.role, content='Hello! ' + last.content),))


class HelloPlugin(Plugin):
    def __init__(self):
        super().__init__(PluginManifest(id='org.uai.hello', name='Hello', version='0.1.0',
            compatibility={'core': '>=0.1.0,<1'}, capabilities={'directives'},
            config_schema=HelloConfig.model_json_schema()))

    def register(self, registrar):
        registrar.add_directive(Greeting(name='org.uai.hello.greeting'))

    async def health(self):
        return PluginHealth(status='ok')
