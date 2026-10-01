"""Cost estimation.

AdverSI ships no built-in price list: vendor prices change frequently and a stale
table would silently produce wrong numbers. Supply prices in config or code; when a
price is unknown, cost is reported as ``None`` rather than guessed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from adversi.protocol.outcome import TokenUsage


class Price(BaseModel):
    input_per_mtok: float = Field(ge=0, description="USD per 1M input tokens")
    output_per_mtok: float = Field(ge=0, description="USD per 1M output tokens")

    def cost(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_per_mtok + usage.output_tokens * self.output_per_mtok
        ) / 1_000_000
