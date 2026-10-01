"""Quickstart: the default research-grade adversarial workflow in a few lines.

export OPENAI_API_KEY=...            # or ANTHROPIC_API_KEY, GEMINI_API_KEY, or run Ollama
export ADVERSI_MODEL=openai:gpt-4o-mini
python examples/quickstart.py
"""

import os

from adversi import AdverSI

ai = AdverSI(
    os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini"),
    mode="research",  # interpret -> independent analysts -> research -> debate -> cross-exam -> critique -> judge -> synthesis
    profile="fast",  # fast | balanced | deep
    tools=["calculator", "fetch_url"],
)

result = ai.run_sync(
    "Does a four-day work week improve productivity at software companies?",
)

print(result.to_markdown())
result.save(
    "quickstart-result.json"
)  # open in the web UI or `adversi inspect quickstart-result.json`
