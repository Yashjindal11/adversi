"""Research question with live web retrieval.

Requires BRAVE_API_KEY for web_search. Search snippets are recorded as weak
``web_search_snippet`` sources; the researcher is instructed to fetch pages, and
citations are verified against the fetched page text.
"""

import os

from adversi import AdverSI, JSONLSink

trace = JSONLSink("research-trace.jsonl")
ai = AdverSI(
    os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini"),
    mode="research",
    profile="balanced",
    tools=["web_search", "fetch_url"],
)
try:
    result = ai.run_sync(
        "Is there good evidence that intermittent fasting improves long-term weight loss "
        "compared with continuous calorie restriction?",
        on_event=trace,
    )
finally:
    trace.close()

print(result.to_markdown())
external = [e for e in result.evidence if e.is_external]
print(
    f"{len(external)} verified external excerpts from {len({e.source_id for e in external})} sources"
)
