"""CrashTest CLI — Typer application."""

from __future__ import annotations

import json
from typing import Optional

import typer

from . import replay, report, store

app = typer.Typer(
    name="crashtest",
    help="Record adversarial agent failures as JSON cassettes; replay them as regression tests.",
    no_args_is_help=True,
    invoke_without_command=False,
)


@app.command("list")
def list_cassettes() -> None:
    """List all recorded cassettes."""
    ids = store.list_cassettes()
    if not ids:
        typer.echo("No cassettes found.")
        raise typer.Exit()
    for cid in ids:
        cassette = store.load(cid)
        verdict_color = {
            "PASS": typer.colors.GREEN,
            "CRASH": typer.colors.RED,
            "DIVERGED": typer.colors.YELLOW,
        }.get(cassette.recorded_verdict, typer.colors.WHITE)
        typer.echo(
            typer.style(f"  [{cassette.recorded_verdict}]", fg=verdict_color)
            + f"  {cid} — {cassette.title}"
        )


@app.command("record")
def record_cassette(scenario_id: str) -> None:
    """Record a cassette by running a scenario against the live agent."""
    from .recorder import record

    typer.echo(f"Recording scenario: {scenario_id}")
    try:
        cassette = record(scenario_id)
    except FileNotFoundError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    verdict_color = typer.colors.GREEN if cassette.recorded_verdict == "PASS" else typer.colors.RED
    typer.echo(
        f"Saved cassette: {cassette.cassette_id} "
        f"({len(cassette.turns)} turns)"
    )
    typer.secho(
        f"Verdict: {cassette.recorded_verdict}",
        fg=verdict_color,
        bold=True,
    )
    if cassette.crash_turn is not None:
        typer.secho(f"Crash turn: {cassette.crash_turn}", fg=typer.colors.RED)


@app.command("show")
def show_cassette(cassette_id: str) -> None:
    """Show a cassette turn-by-turn, with the crash turn marked."""
    try:
        cassette = store.load(cassette_id)
    except FileNotFoundError:
        typer.secho(f"Cassette not found: {cassette_id}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    # Header
    typer.secho(f"\n{'=' * 60}", fg=typer.colors.BRIGHT_BLACK)
    typer.secho(f"  {cassette.title}", bold=True)
    typer.secho(f"  Kind: {cassette.kind}  |  Persona: {cassette.persona}")
    typer.secho(f"  Recorded: {cassette.recorded_at.isoformat()}")
    verdict_color = {
        "PASS": typer.colors.GREEN,
        "CRASH": typer.colors.RED,
        "DIVERGED": typer.colors.YELLOW,
    }.get(cassette.recorded_verdict, typer.colors.WHITE)
    typer.secho(
        f"  Verdict: {cassette.recorded_verdict}",
        fg=verdict_color,
        bold=True,
    )
    if cassette.crash_turn is not None:
        typer.secho(f"  Crash turn: {cassette.crash_turn}", fg=typer.colors.RED)
    typer.secho(f"{'=' * 60}\n", fg=typer.colors.BRIGHT_BLACK)

    # Turns
    for turn in cassette.turns:
        is_crash = (turn.n == cassette.crash_turn)
        prefix = "💥 " if is_crash else "   "

        role_colors = {
            "attacker": typer.colors.CYAN,
            "agent": typer.colors.GREEN,
            "tool": typer.colors.YELLOW,
        }
        role_color = role_colors.get(turn.role, typer.colors.WHITE)
        role_label = turn.role.upper()

        if is_crash:
            typer.secho(f"{prefix}[Turn {turn.n}] {role_label}", fg=typer.colors.RED, bold=True)
        else:
            typer.secho(f"{prefix}[Turn {turn.n}] {role_label}", fg=role_color, bold=True)

        if turn.content:
            content_lines = turn.content.strip().split("\n")
            for line in content_lines:
                typer.echo(f"   {line}")

        if turn.tool_calls:
            for tc in turn.tool_calls:
                typer.secho(
                    f"   → {tc.name}({json.dumps(tc.args)})",
                    fg=typer.colors.MAGENTA,
                )
                if is_crash:
                    typer.secho("     ⬆ THIS CALL VIOLATED AN ASSERTION", fg=typer.colors.RED, bold=True)

        if turn.tool_name:
            typer.secho(f"   tool: {turn.tool_name}", fg=typer.colors.BRIGHT_BLACK)

        typer.echo()

    # Assertions
    typer.secho("Assertions:", bold=True)
    for a in cassette.assertions:
        typer.echo(f"  • {a.type}: {a.tool or ''} {a.value or ''} {a.rule or ''}")

    typer.echo()


@app.command("replay")
def replay_cassette(
    cassette_id: Optional[str] = typer.Argument(None, help="ID of cassette to replay"),
    mode: str = typer.Option("frozen", "--mode", help="Replay mode (frozen or verify)"),
    runs: int = typer.Option(1, "--runs", "-n", help="Number of replay runs"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON results"),
    all_cassettes: bool = typer.Option(False, "--all", help="Replay all recorded cassettes"),
    failing_only: bool = typer.Option(False, "--failing", help="Replay only cassettes with recorded_verdict CRASH"),
) -> None:
    """Replay one or all cassettes and report verdicts."""
    if failing_only:
        all_cassettes = True

    if not all_cassettes and not cassette_id:
        typer.secho("Error: Must specify a cassette_id, --all, or --failing", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    if mode not in ("frozen", "verify"):
        typer.secho(f"Error: Unsupported replay mode '{mode}' (must be frozen or verify)", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    target_ids = store.list_cassettes() if all_cassettes else [cassette_id]

    if not target_ids:
        typer.secho("No cassettes found.", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    if failing_only:
        filtered = []
        for cid in target_ids:
            c = store.load(cid)
            if c.recorded_verdict == "CRASH":
                filtered.append(cid)
        target_ids = filtered
        if not target_ids:
            if json_output:
                typer.echo("[]")
            else:
                typer.echo("No failing cassettes found.")
            raise typer.Exit(code=0)

    results_with_cassettes = []
    any_crash = False
    any_broken = False

    for cid in target_ids:
        try:
            c = store.load(cid)
            if mode == "frozen":
                res = replay.frozen(c, runs=runs)
            else:
                res = replay.verify(c, runs=runs)
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=3)

        results_with_cassettes.append((res, c))

        if "CRASH" in res.verdicts:
            if c.kind == "benign":
                any_broken = True
            else:
                any_crash = True

        if failing_only and json_output:
            _emit_failing_diagnostic(c, res)
        elif json_output:
            typer.echo(report.render_json(res))
        elif not all_cassettes:
            report.render_terminal(res)

    if all_cassettes and not json_output and not failing_only:
        report.render_suite_table(results_with_cassettes)
    elif failing_only and not json_output:
        report.render_suite_table(results_with_cassettes)

    if any_broken:
        raise typer.Exit(code=2)
    elif any_crash:
        raise typer.Exit(code=1)
    else:
        raise typer.Exit(code=0)


def _emit_failing_diagnostic(cassette, result) -> None:
    """Emit compact JSON diagnostic for a failing cassette (for coding agents)."""
    from crashtest import assertions as assert_mod

    offending_tool_call = None
    observed_args = None
    if cassette.crash_turn is not None:
        for turn in cassette.turns:
            if turn.n == cassette.crash_turn and turn.role == "agent":
                if turn.tool_calls:
                    tc = turn.tool_calls[0]
                    offending_tool_call = tc.name
                    observed_args = tc.args

    eval_res = assert_mod.evaluate(cassette.assertions, cassette.turns)

    diagnostic = {
        "id": cassette.cassette_id,
        "crash_turn": cassette.crash_turn,
        "offending_tool_call": offending_tool_call,
        "failed_assertion": eval_res.failed_assertion or result.failed_assertion,
        "observed_args": observed_args,
    }
    typer.echo(json.dumps(diagnostic, indent=2))


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number"),
) -> None:
    """Start the CrashTest FastAPI HTTP server."""
    import uvicorn

    typer.echo(f"Starting CrashTest server on http://{host}:{port}")
    uvicorn.run("crashtest.api:app", host=host, port=port, log_level="info")


@app.command("version")
def version() -> None:
    """Print CrashTest version."""
    typer.echo("crashtest 0.1.0")
