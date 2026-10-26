"""Optional worker telemetry helpers."""
from uai_core.telemetry import configure_telemetry, get_telemetry


def telemetry():
    return get_telemetry('uai-worker')


def configure():
    return configure_telemetry('uai-worker')
