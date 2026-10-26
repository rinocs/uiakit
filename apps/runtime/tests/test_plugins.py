import unittest
from pydantic import BaseModel, ConfigDict
from uai_core.directives import Directive, DirectiveRegistry
from uai_plugin_sdk.plugin import Plugin
from uai_plugin_sdk.manifest import PluginManifest
from uai_runtime.plugin_manager import PluginManager


class Config(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prefix: str = 'hello'


class Example(Plugin):
    def __init__(self, name='org.example', dependencies=()):
        super().__init__(PluginManifest(id=name, name=name, version='1',
            compatibility={'core': '>=0.1'}, capabilities={'directives'}, dependencies=dependencies))
        self.fail = False
        self.stopped = False

    def register(self, registrar):
        registrar.add_directive(Directive(self.manifest.id + '.hello'))
        if self.fail:
            raise RuntimeError('secret')

    async def deactivate(self):
        self.stopped = True


class PluginsTest(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_registration_and_deactivation(self):
        plugin = Example()
        manager = PluginManager([(plugin, Config)])
        before = manager.snapshot()
        self.assertTrue(await manager.activate('org.example', {}))
        active = manager.snapshot()
        self.assertEqual(active.directives.build(('org.example.hello',)).names, ('org.example.hello',))
        with self.assertRaises(ValueError):
            before.directives.build(('org.example.hello',))
        self.assertTrue(await manager.deactivate('org.example'))
        self.assertTrue(plugin.stopped)
        with self.assertRaises(ValueError):
            manager.snapshot().directives.build(('org.example.hello',))
        self.assertEqual(active.directives.build(('org.example.hello',)).names, ('org.example.hello',))

    async def test_failure_and_config_are_isolated(self):
        plugin = Example()
        manager = PluginManager([(plugin, Config)])
        self.assertFalse(await manager.activate('org.example', {'unknown': 'secret'}))
        plugin.fail = True
        self.assertFalse(await manager.activate('org.example', {}))
        self.assertEqual(manager.status()['org.example'], 'failed')
        with self.assertRaises(ValueError):
            manager.snapshot().directives.build(('org.example.hello',))

    async def test_namespace_and_host_collision(self):
        class Bad(Example):
            def register(self, registrar):
                registrar.add_directive(Directive('builtin.escape'))
        manager = PluginManager([(Bad(), Config)])
        self.assertFalse(await manager.activate('org.example', {}))
        base = DirectiveRegistry()
        base.register(Directive('org.example.hello'), mandatory=True)
        manager = PluginManager([(Example(), Config)], directives=base)
        self.assertFalse(await manager.activate('org.example', {}))
        self.assertEqual(manager.snapshot().directives.build().names, ('org.example.hello',))

    async def test_dependencies_block_activation_and_removal(self):
        parent = Example()
        child = Example('org.child', ({'id': 'org.example', 'version': '>=1'},))
        manager = PluginManager([(child, Config), (parent, Config)])
        self.assertFalse(await manager.activate('org.child', {}))
        self.assertTrue(await manager.activate('org.example', {}))
        self.assertTrue(await manager.activate('org.child', {}))
        self.assertFalse(await manager.deactivate('org.example'))
        self.assertTrue(await manager.deactivate('org.child'))
        self.assertTrue(await manager.deactivate('org.example'))

    async def test_tools_removed_even_when_cleanup_fails(self):
        from uai_core.builtin.tools.text_stats import definition, TextStatsInput, TextStatsOutput, text_stats
        class Tools(Example):
            def __init__(self):
                Plugin.__init__(self, PluginManifest(id='org.tools', name='tools', version='1',
                    compatibility={'core': '>=0.1'}, capabilities={'tools'}))

            def register(self, registrar):
                registrar.add_tool(definition().model_copy(update={'id': 'org.tools.stats'}),
                    input_model=TextStatsInput, output_model=TextStatsOutput, handler=text_stats)

            async def deactivate(self):
                raise RuntimeError('private error')

        manager = PluginManager([(Tools(), Config)])
        self.assertTrue(await manager.activate('org.tools', {}))
        self.assertEqual([tool.id for tool in manager.snapshot().tools.catalog()], ['org.tools.stats'])
        self.assertFalse(await manager.deactivate('org.tools'))
        self.assertEqual(manager.snapshot().tools.catalog(), [])
        self.assertEqual(manager.status()['org.tools'], 'failed')

    async def test_activation_failure_cleanup_and_snapshot_membership(self):
        class Failing(Example):
            async def activate(self, config):
                raise RuntimeError('private error')
        plugin = Failing()
        manager = PluginManager([(plugin, Config)])
        self.assertFalse(await manager.activate('org.example', {}))
        self.assertTrue(plugin.stopped)
        detached = manager.snapshot()
        detached.directives.register(Directive('host.local'))
        with self.assertRaises(ValueError):
            manager.snapshot().directives.build(('host.local',))

    def test_configuration_schema_must_match_host_validator(self):
        plugin = Example()
        plugin._manifest = plugin.manifest.model_copy(update={'config_schema': {'type': 'string'}}).model_dump_json()
        with self.assertRaisesRegex(ValueError, 'plugin_config_schema_mismatch'):
            PluginManager([(plugin, Config)])

    async def test_health_failure_is_sanitized(self):
        class Unhealthy(Example):
            async def health(self):
                raise RuntimeError('secret')
        manager = PluginManager([(Unhealthy(), Config)])
        self.assertEqual((await manager.health('org.example')).status, 'unavailable')
        self.assertTrue(await manager.activate('org.example', {}))
        self.assertEqual((await manager.health('org.example')).status, 'unavailable')

    async def test_registrar_closes_after_registration(self):
        class Retains(Example):
            def register(self, registrar):
                super().register(registrar)
                self.registrar = registrar
        plugin = Retains()
        manager = PluginManager([(plugin, Config)])
        self.assertTrue(await manager.activate('org.example', {}))
        with self.assertRaisesRegex(ValueError, 'plugin_registration_closed'):
            plugin.registrar.add_directive(Directive('org.example.late'))

    async def test_hello_installed_and_selected_per_assistant(self):
        from uai_plugin_hello import HelloPlugin, HelloConfig
        from test_directives import context
        manager = PluginManager([(HelloPlugin(), HelloConfig)])
        self.assertTrue(await manager.activate('org.uai.hello', {}))
        registry = manager.snapshot().directives
        unchanged = await registry.build().apply('before_model', context())
        changed = await registry.build(('org.uai.hello.greeting',)).apply('before_model', context())
        self.assertEqual(unchanged.model_input.messages[-1].content, 'Hi')
        self.assertEqual(changed.model_input.messages[-1].content, 'Hello! Hi')

    async def test_active_execution_blocks_cleanup(self):
        manager = PluginManager([(Example(), Config)])
        self.assertTrue(await manager.activate('org.example', {}))
        with manager.execution() as snapshot:
            self.assertIn('org.example.hello', snapshot.directives.build(('org.example.hello',)).names)
            self.assertFalse(await manager.deactivate('org.example'))
        self.assertTrue(await manager.deactivate('org.example'))

    async def test_runtime_plugin_lifecycle_and_assistant_selection(self):
        import httpx
        import json
        from uuid import uuid4
        from uai_runtime.app import create_app
        from uai_runtime.provider import OpenAIProvider
        from uai_plugin_hello import HelloPlugin, HelloConfig
        from test_runtime import request_body, events
        seen = []

        def provider(request):
            text = json.loads(request.content)['messages'][-1]['content']
            seen.append(text)
            return httpx.Response(200, text='data: ' + json.dumps({'choices': [{'delta': {'content': text}, 'finish_reason': 'stop'}]}) + '\n\ndata: [DONE]\n\n')

        app = create_app('internal-secret', OpenAIProvider('http://provider/v1', '',
            transport=httpx.MockTransport(provider)), approved_plugins=[(HelloPlugin(), HelloConfig)])
        headers = {'Authorization': 'Bearer internal-secret'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as client:
            path = '/internal/v1/plugins/org.uai.hello'
            self.assertEqual((await client.post(path + '/activate', json={})).status_code, 401)
            self.assertEqual((await client.get('/internal/v1/plugins', headers=headers)).json()[0]['state'], 'inactive')
            self.assertEqual((await client.post(path + '/activate', json={}, headers=headers)).status_code, 204)
            body = request_body()
            self.assertEqual((await client.post('/internal/v1/runs', json=body, headers=headers)).status_code, 200)
            body['assistant'] = dict(id=str(uuid4()), version=1, name='hello', model='test',
                system_prompt='Helpful', directives=['org.uai.hello.greeting'])
            response = await client.post('/internal/v1/runs', json=body, headers=headers)
            self.assertEqual(events(response)[-1]['payload']['text'], 'Hello! Ciao')
            self.assertEqual(seen, ['Ciao', 'Hello! Ciao'])
            self.assertEqual((await client.post(path + '/deactivate', headers=headers)).status_code, 204)
            self.assertEqual((await client.post('/internal/v1/runs', json=body, headers=headers)).status_code, 422)
            # A failed preflight releases its execution lease too.
            self.assertTrue(await app.state.plugin_manager.activate('org.uai.hello', {}))
            self.assertTrue(await app.state.plugin_manager.deactivate('org.uai.hello'))

    async def test_http_stream_pins_plugin_until_completion(self):
        import asyncio
        import httpx
        from uai_runtime.app import create_app
        from uai_core.providers import ModelChunk
        from test_runtime import request_body
        started, finish = asyncio.Event(), asyncio.Event()

        class Slow:
            async def stream(self, request):
                started.set()
                await finish.wait()
                yield ModelChunk(text='done')

        app = create_app('internal-secret', Slow(), approved_plugins=[(Example(), Config)])
        headers = {'Authorization': 'Bearer internal-secret'}
        path = '/internal/v1/plugins/org.example'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as client:
            await client.post(path + '/activate', json={}, headers=headers)
            pending = asyncio.create_task(client.post('/internal/v1/runs', json=request_body(), headers=headers))
            try:
                await asyncio.wait_for(started.wait(), 1)
                response = await client.post(path + '/deactivate', headers=headers)
                self.assertEqual(response.status_code, 409)
            finally:
                finish.set()
                await pending
            self.assertEqual((await client.post(path + '/deactivate', headers=headers)).status_code, 204)

    async def test_disconnect_before_first_frame_releases_execution(self):
        import json
        from uai_runtime.app import create_app
        from test_runtime import request_body
        manager_app = create_app('internal-secret', object(), approved_plugins=[(Example(), Config)])
        manager = manager_app.state.plugin_manager
        await manager.activate('org.example', {})
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'method': 'POST', 'path': '/internal/v1/runs', 'raw_path': b'/internal/v1/runs',
                 'query_string': b'', 'headers': [(b'authorization', b'Bearer internal-secret'),
                     (b'content-type', b'application/json')], 'scheme': 'http',
                 'server': ('runtime', 80), 'client': ('gateway', 123)}

        async def receive():
            return {'type': 'http.request', 'body': json.dumps(request_body()).encode(), 'more_body': False}

        sent = []

        async def send(message):
            sent.append(message)
            raise OSError('client disconnected before first frame')

        with self.assertRaises(Exception):
            await manager_app(scope, receive, send)
        self.assertEqual(sent[0]['status'], 200)
        self.assertTrue(await manager.deactivate('org.example'))

    async def test_reconcile_is_idempotent_and_restart_recovers(self):
        desired = {'org.example': {'enabled': True, 'config': {'prefix': 'saved'}}}
        manager = PluginManager([(Example(), Config)])
        self.assertTrue(await manager.reconcile(2, desired))
        self.assertTrue(await manager.reconcile(2, desired))
        restarted = PluginManager([(Example(), Config)])
        self.assertTrue(await restarted.reconcile(2, desired))
        self.assertEqual(restarted.status()['org.example'], 'active')
        self.assertFalse(await restarted.reconcile(1, {}))
        with self.assertRaises(ValueError):
            restarted.validate_configuration({'unknown.plugin': {'enabled': True, 'config': {}}})

    async def test_reconfigure_drains_and_failed_activation_does_not_block_core(self):
        manager = PluginManager([(Example(), Config)])
        self.assertTrue(await manager.reconcile(2, {'org.example': {'enabled': True, 'config': {}}}))
        with manager.execution():
            self.assertFalse(await manager.reconcile(3, {'org.example': {'enabled': False, 'config': {}}}))
            with self.assertRaisesRegex(ValueError, 'plugin_configuration_pending'):
                with manager.execution():
                    pass
        self.assertTrue(await manager.reconcile(3, {'org.example': {'enabled': False, 'config': {}}}))
        plugin = Example()
        plugin.fail = True
        broken = PluginManager([(plugin, Config)])
        self.assertFalse(await broken.reconcile(1, {'org.example': {'enabled': True, 'config': {}}}))
        with broken.execution() as snapshot:
            self.assertEqual(snapshot.directives.build().names, ())

    async def test_reconfiguration_restarts_dependency_chain_and_rejects_revision_reuse(self):
        parent = Example()
        child = Example('org.child', ({'id': 'org.example', 'version': '>=1'},))
        manager = PluginManager([(child, Config), (parent, Config)])
        settings = {key: {'enabled': True, 'config': {}} for key in ('org.example', 'org.child')}
        self.assertTrue(await manager.reconcile(1, settings))
        settings['org.example']['config'] = {'prefix': 'changed'}
        self.assertFalse(await manager.reconcile(1, settings))
        self.assertTrue(await manager.reconcile(2, settings))
        self.assertTrue(parent.stopped and child.stopped)
        self.assertEqual(manager.status(), {'org.child': 'active', 'org.example': 'active'})
        with self.assertRaisesRegex(ValueError, 'plugin_missing_enabled_dependency'):
            manager.validate_configuration({'org.child': {'enabled': True, 'config': {}}})

    async def test_private_reconciliation_contract_auth_and_validation(self):
        import httpx
        from uai_runtime.app import create_app
        app = create_app('internal-secret', object(), approved_plugins=[(Example(), Config)])
        headers = {'Authorization': 'Bearer internal-secret'}
        desired = {'revision': 3, 'settings': {'org.example': {'enabled': True, 'config': {}}}}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as client:
            path = '/internal/v1/plugins/'
            self.assertEqual((await client.post(path + 'reconcile', json=desired)).status_code, 401)
            self.assertEqual((await client.post(path + 'validate', json=desired, headers=headers)).status_code, 204)
            response = await client.post(path + 'reconcile', json=desired, headers=headers)
            self.assertEqual(response.json(), {'applied': True, 'revision': 3})
            desired['settings']['unknown.plugin'] = {'enabled': True, 'config': {}}
            self.assertEqual((await client.post(path + 'validate', json=desired, headers=headers)).status_code, 422)
            self.assertEqual(app.state.plugin_manager.status()['org.example'], 'active')

    async def test_plugin_self_cancellation_is_isolated_but_request_cancellation_propagates(self):
        import asyncio
        class Cancels(Example):
            async def activate(self, config):
                raise asyncio.CancelledError()
        manager = PluginManager([(Cancels(), Config)])
        self.assertFalse(await manager.reconcile(1, {'org.example': {'enabled': True, 'config': {}}}))
        self.assertEqual(manager.status()['org.example'], 'failed')

        started = asyncio.Event()
        class Waits(Example):
            async def activate(self, config):
                started.set()
                await asyncio.Event().wait()
        plugin = Waits()
        pending_manager = PluginManager([(plugin, Config)])
        task = asyncio.create_task(pending_manager.activate('org.example', {}))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(plugin.stopped)

    async def test_config_budget_applies_to_normalized_defaults_too(self):
        class LargeConfig(BaseModel):
            model_config = ConfigDict(extra='forbid')
            payload: str = 'x' * 32769
        manager = PluginManager([(Example(), LargeConfig)])
        self.assertFalse(await manager.activate('org.example', {}))
        with self.assertRaises(ValueError):
            manager.validate_configuration({'org.example': {'enabled': True, 'config': {}}})

    async def test_plugin_cannot_mutate_host_configuration_tracking(self):
        class Mutates(Example):
            async def activate(self, config):
                config['prefix'] = 'plugin local state'
        manager = PluginManager([(Mutates(), Config)])
        self.assertTrue(await manager.reconcile(1, {'org.example': {'enabled': True, 'config': {}}}))
        with manager.execution():
            pass
