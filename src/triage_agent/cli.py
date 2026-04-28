"""CLI entry point for the dbt triage agent."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .agent import DbtTriageAgent
from .models import DbtManifest, DbtRunResults, TriageInput

load_dotenv()


@click.group()
@click.version_option(package_name="pipeline-triage-agent")
def cli() -> None:
    """dbt Pipeline Failure Triage Agent — powered by Claude."""


@cli.command()
@click.option(
    "--run-results", "-r",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to run_results.json",
)
@click.option(
    "--manifest", "-m",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to manifest.json (enables deeper SQL + dependency analysis)",
)
@click.option(
    "--log-file", "-l",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to dbt.log",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write report to file instead of stdout",
)
@click.option(
    "--target", "-t",
    default=None,
    help="dbt target name (e.g. prod, dev) — used for context only",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model ID",
)
@click.option(
    "--max-iterations",
    default=15,
    show_default=True,
    type=int,
    help="Max agent investigation iterations",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Print tool calls and results to stderr during investigation",
)
@click.option(
    "--autofix",
    is_flag=True,
    help="Automatically apply the generated fix to the source file if the agent produces one",
)
def triage(
    run_results: str,
    manifest: str | None,
    log_file: str | None,
    output: str,
    output_file: str | None,
    target: str | None,
    api_key: str | None,
    model: str,
    max_iterations: int,
    verbose: bool,
    autofix: bool,
) -> None:
    """
    Triage a dbt pipeline failure and generate a remediation report.

    \b
    Example:
        dbt-triage triage \\
            --run-results ./target/run_results.json \\
            --manifest ./target/manifest.json \\
            --verbose
    """
    if not api_key:
        click.echo("Error: ANTHROPIC_API_KEY is not set. Use --api-key or set the env var.", err=True)
        sys.exit(1)

    click.echo("Loading dbt artifacts...", err=True)
    run_results_data = DbtRunResults.from_path(run_results)

    manifest_data: DbtManifest | None = None
    if manifest:
        manifest_data = DbtManifest.from_path(manifest)

    dbt_log = ""
    if log_file:
        dbt_log = Path(log_file).read_text()

    failures = run_results_data.get_failures()
    if not failures:
        click.echo("No failures found in run_results.json — nothing to triage.", err=True)
        sys.exit(0)

    click.echo(
        f"Found {len(failures)} failure(s). Starting investigation with {model}...",
        err=True,
    )

    triage_input = TriageInput(
        run_results_path=run_results,
        manifest_path=manifest,
        run_results=run_results_data,
        dbt_log=dbt_log,
        manifest=manifest_data,
        target=target,
        autofix=autofix,
    )

    agent = DbtTriageAgent(
        api_key=api_key,
        model=model,
        max_iterations=max_iterations,
        verbose=verbose,
    )
    report = agent.triage(triage_input)

    if output == "json":
        content = json.dumps(report.model_dump(), indent=2)
    else:
        content = report.to_markdown()

    if output_file:
        Path(output_file).write_text(content)
        click.echo(f"Report written to {output_file}", err=True)
    else:
        click.echo(content)

    if autofix:
        if not report.fixes:
            click.echo("Autofix: agent did not produce a fix for this failure type.", err=True)
        elif not manifest:
            click.echo("Warning: --autofix requires --manifest to resolve file paths.", err=True)
        else:
            project_root = Path(manifest).parent.parent
            for fix in report.fixes:
                target_file = project_root / fix.file_path
                if not target_file.exists():
                    click.echo(f"Autofix: target file not found: {target_file}", err=True)
                else:
                    target_file.write_text(fix.content)
                    click.echo(f"Autofix applied: {target_file}", err=True)


@cli.command()
@click.option(
    "--scenario",
    type=click.Choice(["sql_error", "missing_ref"]),
    default="sql_error",
    show_default=True,
    help="Which built-in failure scenario to run",
)
@click.option("--api-key", envvar="ANTHROPIC_API_KEY", default=None)
@click.option("--verbose", "-v", is_flag=True)
def demo(scenario: str, api_key: str | None, verbose: bool) -> None:
    """Run the agent against a built-in sample failure scenario."""
    import importlib.resources as pkg_resources

    fixtures_base = Path(__file__).parent.parent.parent / "examples" / "target"
    run_results_path = str(fixtures_base / "run_results.json")
    manifest_path = str(fixtures_base / "manifest.json")

    for p in (run_results_path, manifest_path):
        if not Path(p).exists():
            click.echo(
                f"Sample fixture not found: {p}\n"
                "Run from the repo root after cloning, or generate fixtures with:\n"
                "  python examples/generate_fixtures.py",
                err=True,
            )
            sys.exit(1)

    click.echo(f"Running demo scenario: {scenario}", err=True)
    ctx = click.get_current_context()
    ctx.invoke(
        triage,
        run_results=run_results_path,
        manifest=manifest_path,
        log_file=None,
        output="markdown",
        output_file=None,
        target="prod",
        api_key=api_key,
        model="claude-sonnet-4-6",
        max_iterations=15,
        verbose=verbose,
    )


if __name__ == "__main__":
    cli()
