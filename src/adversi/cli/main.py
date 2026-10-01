"""``adversi`` command-line interface (stdlib argparse; no extra dependencies)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from adversi._version import __version__
from adversi.errors import AdverSIError

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


def _progress_printer(stream: TextIO) -> Any:
    from adversi.observability.events import Event, EventType

    def handler(event: Event) -> None:
        d = event.data
        if event.type == EventType.STEP_STARTED:
            print(f"  > {event.step}", file=stream, flush=True)
        elif event.type == EventType.AGENT_COMPLETED:
            print(f"      {event.agent} done ({d.get('duration_s')}s)", file=stream, flush=True)
        elif event.type in (EventType.STEP_FAILED, EventType.AGENT_FAILED):
            print(
                f"    ! {event.step} {event.agent or ''}: {d.get('error')}", file=stream, flush=True
            )
        elif event.type == EventType.TOOL_CALL:
            print(f"      {event.agent} -> {d.get('tool')}", file=stream, flush=True)
        elif event.type in (EventType.WARNING, EventType.BUDGET_EXCEEDED):
            print(f"    ! {d.get('message')}", file=stream, flush=True)

    return handler


def _render(result: Any, fmt: str) -> str:
    if fmt == "json":
        return str(result.to_json())
    if fmt == "html":
        return str(result.to_html())
    return str(result.to_markdown())


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
        print(f"wrote {output}", file=sys.stderr)
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


# -- commands -----------------------------------------------------------------------


def cmd_run(args: argparse.Namespace, *, mode: str | None = None) -> int:
    from adversi.api import AdverSI
    from adversi.config.loader import load_config
    from adversi.config.schema import ToolConfig
    from adversi.observability.sinks import JSONLSink
    from adversi.tools.documents import load_documents

    config = load_config(args.config)
    for name in args.tool or []:
        if name not in [t.name for t in config.tools]:
            config.tools.append(ToolConfig(name=name))
    if args.domain:
        config.workflow.domain = args.domain
    for key in ("analysts", "debate_rounds"):
        value = getattr(args, key, None)
        if value is not None:
            setattr(config.workflow, key, value)
    ai = AdverSI.from_config(config, model=args.model, mode=mode or args.mode, profile=args.profile)

    handlers: list[Any] = []
    sink = None
    if not args.quiet:
        handlers.append(_progress_printer(sys.stderr))
    if args.trace:
        sink = JSONLSink(args.trace)
        handlers.append(sink)
    documents = load_documents(args.doc or [])
    if not args.quiet:
        wf = ai.workflow
        print(
            f"AdverSI {__version__}: mode={wf.mode} profile={wf.profile} steps={len(wf.steps)}",
            file=sys.stderr,
        )
    try:
        result = ai.run_sync(
            args.question, documents=documents, context=args.context, on_event=handlers
        )
    finally:
        if sink:
            sink.close()
    fmt = args.format or config.output.format
    if args.save:
        result.save(args.save, "json")
        print(f"saved result to {args.save}", file=sys.stderr)
    _emit(_render(result, fmt), args.output)
    return EXIT_OK if result.metadata.status.value != "failed" else EXIT_ERROR


def cmd_init(args: argparse.Namespace) -> int:
    from adversi.config.template import CONFIG_TEMPLATE

    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return EXIT_USAGE
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    print(
        f'created {path}. Set your provider API key env var, then: adversi run "<question>"',
        file=sys.stderr,
    )
    return EXIT_OK


def cmd_inspect(args: argparse.Namespace) -> int:
    from adversi.protocol.result import AdverSIResult

    r = AdverSIResult.load(args.result)
    m = r.metadata
    print(f"Question: {r.question}")
    print(f"Run {m.run_id}  mode={m.mode} profile={m.profile} status={m.status.value}")
    print(f"Usage: {m.usage.calls} calls, {m.usage.total_tokens:,} tokens, cost={m.usage.cost_usd}")
    if r.synthesis:
        print(f"\nAnswer: {r.synthesis.answer}")
    counts: dict[str, int] = {}
    for c in r.claims:
        counts[c.status.value] = counts.get(c.status.value, 0) + 1
    print(f"\nClaims: {len(r.claims)} {counts}")
    if args.claims or args.all:
        for c in r.claims:
            print(f"  {c.id:<4} {c.status.value:<20} {c.statement}")
            if c.policy_note:
                print(f"       policy: {c.policy_note}")
    ext = sum(1 for e in r.evidence if e.is_external)
    print(
        f"Evidence: {len(r.evidence)} ({ext} verified external), rejected citations: {len(r.rejected_citations)}"
    )
    if args.evidence or args.all:
        for e in r.evidence:
            print(
                f"  {e.id:<4} {e.provenance.source_type.value:<18} +{e.supports} -{e.contradicts} {e.provenance.uri or ''}"
            )
    print(f"Challenges: {len(r.challenges)}  Critique findings: {len(r.critique)}")
    if args.events or args.all:
        for ev in r.trace:
            print(f"  {ev.seq:>4} {ev.type.value:<20} {ev.step or '':<22} {ev.agent or ''}")
    for err in m.errors:
        print(f"Error: [{err.step}] {err.type}: {err.message}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    from adversi.protocol.result import AdverSIResult

    _emit(_render(AdverSIResult.load(args.result), args.format), args.output)
    return EXIT_OK


def cmd_providers(args: argparse.Namespace) -> int:
    from adversi.providers.registry import available_providers

    if args.json:
        print(
            json.dumps(
                {
                    n: {
                        "description": i.description,
                        "api_key_env": i.api_key_env,
                        "configured": i.configured(),
                        "base_url": i.default_base_url,
                    }
                    for n, i in available_providers().items()
                },
                indent=2,
            )
        )
        return EXIT_OK
    for name, info in sorted(available_providers().items()):
        key = info.api_key_env or "-"
        state = "ready" if info.configured() else f"set {key}"
        print(f"{name:<18} {state:<26} {info.description}")
    return EXIT_OK


def cmd_config(args: argparse.Namespace) -> int:
    from adversi.config.loader import ConfigBuilder, load_config

    config = load_config(args.config)
    if args.action == "show":
        print(json.dumps(config.model_dump(mode="json"), indent=2))
        return EXIT_OK
    wf = ConfigBuilder(config).workflow(default_model=args.model)
    print(json.dumps(wf.describe(), indent=2, default=str))
    print("configuration is valid", file=sys.stderr)
    return EXIT_OK


def cmd_benchmark(args: argparse.Namespace) -> int:
    from adversi.config.loader import ConfigBuilder, load_config
    from adversi.evaluation import load_dataset, make_scorer, run_benchmark

    items = load_dataset(args.dataset)
    if args.limit:
        items = items[: args.limit]
    config = load_config(args.config)
    builder = ConfigBuilder(config)
    systems = {
        mode: builder.workflow(default_model=args.model, mode=mode, profile=args.profile)
        for mode in args.modes.split(",")
    }
    scorer = make_scorer(args.scorer, grader_model=args.grader)
    print(
        f"benchmark: {len(items)} items x {len(systems)} systems, scorer={scorer.name}",
        file=sys.stderr,
    )
    report = asyncio.run(
        run_benchmark(
            items, systems, scorer, concurrency=args.concurrency, output_dir=args.output_dir
        )
    )
    print(report.to_markdown())
    return EXIT_OK


def cmd_evaluate(args: argparse.Namespace) -> int:
    from adversi.evaluation import load_dataset, make_scorer, rescore

    report = asyncio.run(
        rescore(
            args.results_dir,
            load_dataset(args.dataset),
            make_scorer(args.scorer, grader_model=args.grader),
        )
    )
    print(report.to_markdown())
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from adversi.server.app import create_app
    except ImportError:
        print("the web server requires: pip install 'adversi[server]'", file=sys.stderr)
        return EXIT_ERROR
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "warning: the AdverSI server has no authentication; do not expose it publicly.",
            file=sys.stderr,
        )
    uvicorn.run(
        create_app(config_path=args.config, default_model=args.model),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return EXIT_OK


# -- parser -------------------------------------------------------------------------


def _add_run_args(p: argparse.ArgumentParser, *, with_mode: bool) -> None:
    p.add_argument("question")
    p.add_argument("-c", "--config", help="config file (default: ./adversi.toml if present)")
    p.add_argument("-m", "--model", help="default model, e.g. openai:gpt-4o-mini")
    if with_mode:
        p.add_argument(
            "--mode", help="simple | debate | adversarial | research | peer_review | jury"
        )
    p.add_argument("--profile", choices=["fast", "balanced", "deep"])
    p.add_argument(
        "--tool",
        action="append",
        help="enable a tool (repeatable): calculator, fetch_url, web_search",
    )
    p.add_argument(
        "--doc", action="append", help="add a text document as a user-provided source (repeatable)"
    )
    p.add_argument("--context", help="extra context for the question")
    p.add_argument("--domain", help="domain for the domain_expert analyst")
    p.add_argument("--analysts", type=int)
    p.add_argument("--debate-rounds", type=int, dest="debate_rounds")
    p.add_argument("-f", "--format", choices=["json", "markdown", "html"])
    p.add_argument("-o", "--output", help="write the report here instead of stdout")
    p.add_argument("--save", help="also save the full JSON result here")
    p.add_argument("--trace", help="write the event stream as JSONL")
    p.add_argument("-q", "--quiet", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adversi", description="Adversarial, evidence-aware multi-agent reasoning."
    )
    parser.add_argument("--version", action="version", version=f"adversi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create an adversi.toml")
    p.add_argument("--path", default="adversi.toml")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="run a workflow on a question")
    _add_run_args(p, with_mode=True)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("debate", help="shortcut for run --mode debate")
    _add_run_args(p, with_mode=False)
    p.set_defaults(func=lambda a: cmd_run(a, mode="debate"))

    p = sub.add_parser("inspect", help="summarise a saved JSON result")
    p.add_argument("result")
    p.add_argument("--claims", action="store_true")
    p.add_argument("--evidence", action="store_true")
    p.add_argument("--events", action="store_true")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("report", help="render a saved JSON result")
    p.add_argument("result")
    p.add_argument("-f", "--format", choices=["json", "markdown", "html"], default="markdown")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("providers", help="list model providers and credential status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_providers)

    p = sub.add_parser("config", help="show or validate configuration")
    p.add_argument("action", choices=["show", "validate"])
    p.add_argument("-c", "--config")
    p.add_argument("-m", "--model")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("benchmark", help="(experimental) compare modes on a JSONL dataset")
    p.add_argument("dataset")
    p.add_argument("--modes", default="simple,adversarial", help="comma-separated modes")
    p.add_argument("--scorer", default="contains", help="exact_match | contains | llm_grader")
    p.add_argument("--grader", help="model for llm_grader")
    p.add_argument("-c", "--config")
    p.add_argument("-m", "--model")
    p.add_argument("--profile", choices=["fast", "balanced", "deep"])
    p.add_argument("--limit", type=int)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--output-dir", default="benchmark-results")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("evaluate", help="(experimental) re-score saved benchmark results")
    p.add_argument("results_dir")
    p.add_argument("dataset")
    p.add_argument("--scorer", default="contains")
    p.add_argument("--grader")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("serve", help="start the web UI / API (requires adversi[server])")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("-c", "--config")
    p.add_argument("-m", "--model")
    p.set_defaults(func=cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except AdverSIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
