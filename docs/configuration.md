# Configuration

`adversi init` writes a commented `adversi.toml`. The CLI and `AdverSI.from_config()`
read `adversi.toml`, `adversi.yaml` or `adversi.yml` from the current directory, or a
path given with `-c`. Unknown keys are errors.

```toml
version = 1
tools = ["calculator", "fetch_url"]       # top-level keys must come before any [table]

[models]
default = "openai:gpt-4o-mini"            # shorthand
skeptic = "ollama:llama3.1:8b"            # per role
judge_2 = "gemini:gemini-2.0-flash"       # per agent name

[models.judge]                            # full form
model = "anthropic:claude-sonnet-4-5"
temperature = 0.0
max_tokens = 4096
timeout_s = 120
max_retries = 3
max_concurrency = 4
requests_per_minute = 50
price = { input_per_mtok = 3.0, output_per_mtok = 15.0 }

[providers.local]                         # alias with overrides
type = "openai_compatible"
base_url = "http://localhost:8000/v1"
api_key_env = "LOCAL_LLM_KEY"

[workflow]
mode = "research"                         # or set `steps = [...]`
profile = "balanced"
domain = "airline operations"
analysts = 3
debate_rounds = 2
cross_examination_rounds = 1
max_challenges = 6
max_research_claims = 6
max_tool_steps = 4
jurors = 3
max_concurrency = 8
require_external_evidence = true
min_evidence_reliability = 0.3

[[agents]]
role = "skeptic"
name = "red_team"
model = "local:qwen2.5"
instructions = "Focus on safety and regulatory failure modes."

[[agents]]
role = "domain_expert"
domain = "FAA Part 117 crew rest rules"
name = "crew_expert"

[budget]
max_total_tokens = 400000
max_cost_usd = 2.0
max_model_calls = 60

[cache]
enabled = true
path = ".adversi/cache.sqlite"

[output]
format = "markdown"
include_trace = true
```

Notes:

- Agents with role `analyst`, `statistician` or `domain_expert` **replace** the default
  independent analysts. Agents with other roles replace the built-in agent of that role.
- Model resolution: agent `model` > `[models].<agent name>` > `[models].<role>` > `default`
  > `--model` / `ADVERSI_MODEL`.
- Credentials: only `api_key_env` (an environment variable *name*). Keys in config files
  are rejected.
- `adversi config validate` prints the fully resolved workflow (steps, agents, models,
  tools, policy, budget) without running anything.

## YAML

```yaml
models:
  default: openai:gpt-4o-mini
  judge: anthropic:claude-sonnet-4-5
workflow:
  mode: jury
  jurors: 3
tools: [calculator]
```

Requires `pip install "adversi[yaml]"`.
