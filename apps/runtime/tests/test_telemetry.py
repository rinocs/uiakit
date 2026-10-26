from uai_core.telemetry import Telemetry, sanitize_attributes, sanitize_route


def test_sensitive_attributes_are_dropped():
    attrs = sanitize_attributes({
        'prompt': 'private',
        'authorization': 'Bearer secret',
        'content': 'text',
        'run_id': 'run-1',
        'model': 'test-model',
    })
    assert attrs == {'run_id': 'run-1', 'model': 'test-model'}


def test_route_cardinality_is_bounded():
    assert sanitize_route(
        '/v1/conversations/00000000-0000-4000-8000-000000000001/messages'
    ) == '/v1/conversations/{id}/messages'


def test_in_memory_span_excludes_prompt_and_records_metrics():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = Telemetry('test', tracer=provider.get_tracer('test'))
    with telemetry.span('run', {'run_id': 'run-1', 'prompt': 'private'}):
        telemetry.record_event('response.delta')
    span = exporter.get_finished_spans()[0]
    attributes = dict(span.attributes)
    assert attributes['run_id'] == 'run-1'
    assert 'prompt' not in attributes
