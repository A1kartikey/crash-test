"""
Report renderer — terminal formatting, suite table, and JSON output for ReplayResult.
"""

from __future__ import annotations

import json
import typer

from crashtest.schema import Cassette, ReplayResult


def render_terminal(result: ReplayResult) -> None:
    """Render a single ReplayResult to stdout in a terminal-friendly format."""
    is_crash = "CRASH" in result.verdicts
    verdict_color = typer.colors.RED if is_crash else typer.colors.GREEN

    typer.echo()
    typer.secho(
        "════════════════════════════════════════════════════════════",
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.secho(
        f"  Cassette: {result.cassette_id}  [{result.mode.upper()} REPLAY]",
        bold=True,
    )
    typer.secho(
        f"  Verdict:  {result.summary}",
        fg=verdict_color,
        bold=True,
    )

    if is_crash:
        if result.crash_turn is not None:
            typer.secho(f"  Crash Turn: {result.crash_turn}", fg=typer.colors.RED, bold=True)
        if result.failed_assertion:
            typer.secho(f"  Failed Assertion: {result.failed_assertion}", fg=typer.colors.RED)

    typer.secho(f"  Duration: {result.duration_ms} ms", fg=typer.colors.CYAN)
    typer.secho(f"  Network Calls: {result.network_calls}", fg=typer.colors.CYAN)
    typer.secho(
        "════════════════════════════════════════════════════════════",
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.echo()


def render_suite_table(results_with_cassettes: list[tuple[ReplayResult, Cassette]]) -> None:
    """Render a suite summary table with Kind column and distinct BROKEN/CRASH counts."""
    typer.echo()
    typer.secho(
        "═" * 78,
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.secho(
        "  CRASHTEST REPLAY SUITE REPORT",
        bold=True,
    )
    typer.secho(
        "═" * 78,
        fg=typer.colors.BRIGHT_BLACK,
    )

    # Header
    typer.secho(
        f"  {'ID':<10} {'KIND':<13} {'TITLE':<32} {'VERDICT':<10} {'DURATION':<8}",
        bold=True,
    )
    typer.secho(
        "  " + "─" * 74,
        fg=typer.colors.BRIGHT_BLACK,
    )

    pass_count = 0
    crash_count = 0
    broken_count = 0

    for result, cassette in results_with_cassettes:
        is_crash = "CRASH" in result.verdicts

        if cassette.kind == "benign" and is_crash:
            display_verdict = "BROKEN"
            verdict_color = typer.colors.MAGENTA
            broken_count += 1
        elif is_crash:
            display_verdict = "CRASH"
            verdict_color = typer.colors.RED
            crash_count += 1
        else:
            display_verdict = "PASS"
            verdict_color = typer.colors.GREEN
            pass_count += 1

        title_truncated = (cassette.title[:29] + "...") if len(cassette.title) > 32 else cassette.title

        typer.echo(
            f"  {result.cassette_id:<10} "
            f"{cassette.kind:<13} "
            f"{title_truncated:<32} "
            + typer.style(f"{display_verdict:<10}", fg=verdict_color, bold=True)
            + f" {result.duration_ms}ms"
        )

    typer.secho(
        "═" * 78,
        fg=typer.colors.BRIGHT_BLACK,
    )

    # Summary line
    summary_parts = []
    if pass_count > 0:
        summary_parts.append(typer.style(f"{pass_count} PASS", fg=typer.colors.GREEN, bold=True))
    if crash_count > 0:
        summary_parts.append(typer.style(f"{crash_count} CRASH (adversarial failures)", fg=typer.colors.RED, bold=True))
    if broken_count > 0:
        summary_parts.append(typer.style(f"{broken_count} BROKEN (benign failures)", fg=typer.colors.MAGENTA, bold=True))

    typer.echo("  Summary: " + ", ".join(summary_parts))
    typer.secho(
        "═" * 78,
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.echo()


def render_json(result: ReplayResult) -> str:
    """Render ReplayResult as JSON string."""
    return result.model_dump_json(indent=2)
