CONFIG_TEMPLATE = """\
# AdverSI configuration. Full reference: docs/configuration.md
version = 1

# Tools available to tool-using roles (analysts, researcher, statistician).
# web_search needs BRAVE_API_KEY. (Top-level keys must precede all [tables].)
tools = ["calculator", "fetch_url"]

# Models are referenced as "provider:model". Keys under [models] are either
# "default", a role name (skeptic, judge, ...), an agent name, or an alias that
# agents reference with model = "<alias>".
[models]
default = "openai:gpt-4o-mini"
# judge = "anthropic:claude-sonnet-4-5"
# skeptic = "ollama:llama3.1:8b"

# [models.judge]
# model = "anthropic:claude-sonnet-4-5"
# temperature = 0.0
# price = { input_per_mtok = 3.0, output_per_mtok = 15.0 }  # optional; enables cost tracking

# Provider overrides. API keys are read from environment variables only.
# [providers.local]
# type = "openai_compatible"
# base_url = "http://localhost:8000/v1"

[workflow]
mode = "research"        # simple | debate | adversarial | research | peer_review | jury
profile = "balanced"     # fast | balanced | deep
# steps = ["independent_analysis", "claim_consolidation", "cross_examination", "judgment", "synthesis"]
# domain = "airline operations"
# debate_rounds = 2
require_external_evidence = true

# Optional custom agents. Agents with role analyst/statistician/domain_expert
# replace the default independent analysts.
# [[agents]]
# role = "skeptic"
# name = "red_team"
# model = "anthropic:claude-sonnet-4-5"
# instructions = "Focus on safety and regulatory failure modes."

[budget]
# max_total_tokens = 400000
# max_cost_usd = 2.0
# max_model_calls = 60

[cache]
enabled = false
path = ".adversi/cache.sqlite"

[output]
format = "markdown"
include_trace = true
"""
