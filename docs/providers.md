# Model providers

## Using models

```python
from adversi import Model, Price

Model("openai:gpt-4o-mini", temperature=0.2)
Model("ollama:llama3.1:8b")                              # model names may contain ':'
Model("openai_compatible:qwen2.5-32b", provider_options={"base_url": "http://gpu-box:8000/v1"})
Model(
    "anthropic:claude-sonnet-4-5",
    max_tokens=4096, timeout_s=90, max_retries=4,
    max_concurrency=4, requests_per_minute=50,
    price=Price(input_per_mtok=3.0, output_per_mtok=15.0),  # enables cost tracking
)
```

`Model` provides, for every provider:

- **retries** with jittered exponential backoff, only for retryable errors (429, 5xx,
  timeouts, transport errors); never for 4xx or authentication errors
- **timeouts** per call
- **concurrency** (`max_concurrency`) and **rate limiting** (`requests_per_minute`)
- **caching** (`cache=MemoryCache()` or `SQLiteCache(path)`), keyed on the full request
- **token and cost accounting** attributed to the active run, and **budget** checks
- **streaming** via `async for chunk in model.stream(messages)`
- `complete_sync()` for scripts

## Built-in providers

| Name | Base URL | Key env var | Structured output | Tools |
|---|---|---|---|---|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | JSON schema | yes |
| `anthropic` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | prompt + validation + repair | yes |
| `gemini` | Google OpenAI-compatible endpoint | `GEMINI_API_KEY` | JSON schema | yes |
| `ollama` | `http://localhost:11434/v1` | none | JSON schema | yes |
| `huggingface` | `https://router.huggingface.co/v1` | `HF_TOKEN` | prompt + validation | yes |
| `openai_compatible` | set `base_url` | `OPENAI_COMPATIBLE_API_KEY` (optional) | JSON mode | yes |

Override any of them in config:

```toml
[providers.openai]
base_url = "https://my-azure-or-gateway.example.com/v1"
api_key_env = "MY_GATEWAY_KEY"

[providers.vllm]          # a new name aliasing a provider type
type = "openai_compatible"
base_url = "http://gpu-box:8000/v1"
capabilities = { tool_calling = true, json_schema = true }
```

Then use `vllm:Qwen2.5-32B-Instruct` as a model spec.

## Writing a provider

Implement one method:

```python
from adversi import ModelProvider, register_provider
from adversi.providers import ModelRequest, ModelResponse, ProviderCapabilities

class MyProvider(ModelProvider):
    name = "mine"
    capabilities = ProviderCapabilities(tool_calling=False, json_mode=True)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        ...  # translate request.messages / tools / response_schema; return ModelResponse

register_provider("mine", lambda **options: MyProvider(**options))
```

Raise `adversi.errors.ProviderError` (or `RateLimitError`, `AuthenticationError`,
`ProviderTimeoutError`) with an accurate `retryable` flag. Do not implement retries,
caching or accounting; `Model` does that.

Distribute as a package by declaring an entry point:

```toml
[project.entry-points."adversi.providers"]
mine = "my_package:make_provider"
```

See [examples/08_custom_provider.py](../examples/08_custom_provider.py).

## Capabilities and degradation

- No `tool_calling`: agents run without tools and a `warning` event is emitted.
- No `json_schema`/`json_mode`: the schema is in the system prompt; output is parsed
  leniently (code fences, surrounding prose) and validated, with one repair round.
