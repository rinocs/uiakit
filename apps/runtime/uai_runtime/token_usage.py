"""Aggregated token usage that never turns missing provider data into zero."""
from decimal import Decimal

USAGE_KEYS = ('prompt_tokens', 'completion_tokens', 'total_tokens')


def estimate_tokens(text: str) -> int:
    """Conservative provider-neutral estimate, used only when usage is unknown."""
    return (len(text) + 3) // 4


def clean_usage(usage) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    clean = {}
    for key in USAGE_KEYS:
        value = usage.get(key)
        if type(value) is int and value >= 0:
            clean[key] = value
    return clean


class UsageAccumulator:
    def __init__(self):
        self._sums = {key: 0 for key in USAGE_KEYS}
        self._seen: set[str] = set()
        self._missing: set[str] = set()
        self.estimated_tokens = 0

    def record_usage(self, usage) -> None:
        clean = clean_usage(usage)
        for key in USAGE_KEYS:
            if clean is not None and key in clean:
                self._sums[key] += clean[key]
                self._seen.add(key)
            else:
                self._missing.add(key)

    def record_text(self, text: str) -> None:
        self.estimated_tokens += estimate_tokens(text)

    def value(self) -> dict[str, int]:
        return {key: self._sums[key] for key in USAGE_KEYS
                if key in self._seen and key not in self._missing}

    def budget_tokens(self) -> int:
        reported = self.value().get('total_tokens')
        return reported if reported is not None else self.estimated_tokens

    def cost_usd(self, input_per_million: float | None, output_per_million: float | None) -> float | None:
        usage = self.value()
        if (input_per_million is None or output_per_million is None
                or 'prompt_tokens' not in usage or 'completion_tokens' not in usage):
            return None
        cost = (Decimal(usage['prompt_tokens']) * Decimal(str(input_per_million))
                + Decimal(usage['completion_tokens']) * Decimal(str(output_per_million))) / Decimal(1_000_000)
        return float(round(cost, 6))
