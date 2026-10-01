from __future__ import annotations

import json
from pathlib import Path

import pytest

from adversi.cli.main import main
from adversi.config import CONFIG_TEMPLATE, ConfigBuilder, load_config, parse_config
from adversi.errors import ConfigurationError
from adversi.protocol import AdverSIResult
from tests.conftest import QUESTION, world_handler


def test_template_is_valid_and_builds(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    import tomllib

    cfg = parse_config(tomllib.loads(CONFIG_TEMPLATE))
    wf = ConfigBuilder(cfg).workflow()
    assert wf.mode == "research" and wf.profile == "balanced"
    assert wf.models.default and wf.models.default.id == "openai:gpt-4o-mini"
    assert [t.name for t in wf.tools] == ["calculator", "fetch_url"]


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ConfigurationError):
        parse_config({"workflow": {"mdoe": "research"}})


def test_api_keys_cannot_be_put_in_config() -> None:
    with pytest.raises(ConfigurationError):
        parse_config({"providers": {"openai": {"api_key": "sk-123"}}})


def test_role_models_custom_agents_and_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    cfg = parse_config(
        {
            "models": {
                "default": "openai:gpt-4o-mini",
                "judge": {"model": "anthropic:claude-x", "temperature": 0},
            },
            "providers": {
                "local": {"type": "openai_compatible", "base_url": "http://localhost:9/v1"}
            },
            "agents": [
                {
                    "role": "skeptic",
                    "name": "red_team",
                    "model": "local:qwen",
                    "instructions": "Be harsh.",
                },
                {"role": "domain_expert", "domain": "airline operations", "name": "ops"},
                {"role": "statistician"},
            ],
            "workflow": {"mode": "adversarial", "profile": "fast", "max_challenges": 2},
        }
    )
    wf = ConfigBuilder(cfg).workflow()
    ia = next(s for s in wf.steps if s.kind == "independent_analysis")
    assert [a.name for a in ia.agents] == ["ops", "statistician"]
    assert "airline operations" in ia.agents[0].role.instructions
    cx = next(s for s in wf.steps if s.kind == "cross_examination")
    assert cx.challengers[0].name == "red_team"
    assert cx.challengers[0].model and cx.challengers[0].model.id == "openai_compatible:qwen"
    assert cx.max_challenges_per_round == 2
    assert wf.models.overrides["judge"].temperature == 0


def test_custom_step_list(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    cfg = parse_config(
        {
            "models": {"default": "openai:m"},
            "workflow": {"steps": ["single_analysis", "critique", "synthesis"]},
        }
    )
    wf = ConfigBuilder(cfg).workflow()
    assert [s.kind for s in wf.steps] == ["independent_analysis", "critique", "synthesis"]
    with pytest.raises(ConfigurationError):
        ConfigBuilder(
            parse_config({"models": {"default": "openai:m"}, "workflow": {"steps": ["nope"]}})
        ).workflow()


def test_missing_default_model(monkeypatch) -> None:
    monkeypatch.delenv("ADVERSI_MODEL", raising=False)
    with pytest.raises(ConfigurationError, match="no default model"):
        ConfigBuilder(parse_config({})).workflow()


def test_yaml_config(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("yaml")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    p = tmp_path / "adversi.yaml"
    p.write_text("models:\n  default: openai:m\nworkflow:\n  mode: jury\n  jurors: 2\n")
    wf = ConfigBuilder(load_config(p)).workflow()
    jury = next(s for s in wf.steps if s.name == "jury")
    assert len(jury.agents) == 2


# -- CLI ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted((Path(__file__).parents[1] / "examples" / "configs").glob("*"))
)
def test_example_configs_build(path: Path, monkeypatch) -> None:
    if path.suffix in (".yaml", ".yml"):
        pytest.importorskip("yaml")
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(var, "x")
    wf = ConfigBuilder(load_config(path)).workflow()
    assert wf.steps and wf.models.default is not None


def test_cli_config_validate(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    cfg = tmp_path / "adversi.toml"
    cfg.write_text(CONFIG_TEMPLATE)
    assert main(["config", "validate", "-c", str(cfg)]) == 0
    described = json.loads(capsys.readouterr().out)
    assert described["mode"] == "research"
    assert [s["kind"] for s in described["steps"]][-1] == "synthesis"
    assert "api_key" not in json.dumps(described).lower()


def test_cli_init_and_refuse_overwrite(tmp_path: Path, capsys) -> None:
    path = tmp_path / "adversi.toml"
    assert main(["init", "--path", str(path)]) == 0
    assert path.read_text() == CONFIG_TEMPLATE
    assert main(["init", "--path", str(path)]) == 2


def test_cli_run_inspect_report(tmp_path: Path, capsys, register_scripted) -> None:
    register_scripted(world_handler)
    doc = tmp_path / "boiling.txt"
    from tests.conftest import DOC_TEXT

    doc.write_text(DOC_TEXT)
    saved = tmp_path / "result.json"
    code = main(
        [
            "run",
            QUESTION,
            "--model",
            "scripted:m",
            "--doc",
            str(doc),
            "--profile",
            "balanced",
            "--save",
            str(saved),
            "-f",
            "json",
            "-q",
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claims"][0]["status"] == "supported"

    result = AdverSIResult.load(saved)
    assert result.metadata.config["mode"] == "research"

    assert main(["inspect", str(saved), "--all"]) == 0
    text = capsys.readouterr().out
    assert "C1" in text and "verified external" in text

    html = tmp_path / "r.html"
    assert main(["report", str(saved), "-f", "html", "-o", str(html)]) == 0
    assert html.read_text().startswith("<!doctype html>")


def test_cli_debate_shortcut(capsys, register_scripted) -> None:
    provider = register_scripted(world_handler)
    assert main(["debate", QUESTION, "-m", "scripted:m", "-q"]) == 0
    steps = {r.metadata["step"] for r in provider.requests}
    assert steps == {"single_analysis", "debate", "judgment", "synthesis"}
    assert "# Does water always boil" in capsys.readouterr().out


def test_cli_reports_configuration_errors(capsys, monkeypatch) -> None:
    monkeypatch.delenv("ADVERSI_MODEL", raising=False)
    assert main(["run", "q", "-c", "/nonexistent.toml"]) == 1
    assert "config file not found" in capsys.readouterr().err


def test_cli_providers(capsys) -> None:
    assert main(["providers", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"openai", "anthropic", "gemini", "ollama", "huggingface", "openai_compatible"} <= set(
        data
    )
