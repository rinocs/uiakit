"""Metadata-only stage telemetry; lifecycle subscribers remain observational."""
import logging

from ...directives import Directive

logger = logging.getLogger(__name__)


class ObservabilityDirective(Directive):
    def __init__(self):
        super().__init__(name='builtin.observability', priority=4)

    async def before_model(self, context):
        logger.info('builtin_context run_id=%s correlation_id=%s message_count=%d input_chars=%d',
                    context.run_id, context.correlation_id, len(context.model_input.messages),
                    len(context.model_input.system_prompt) + sum(len(m.content) for m in context.model_input.messages))
        return context

    async def after_model(self, context):
        logger.info('builtin_output run_id=%s correlation_id=%s output_chars=%d',
                    context.run_id, context.correlation_id, len(context.model_output or ''))
        return context
