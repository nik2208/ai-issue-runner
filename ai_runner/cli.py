"""Command-line interface for AI Issue Runner."""

import sys
import os
import asyncio
import yaml
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_runner.config import (
    load_config,
    save_config,
    load_credentials,
    export_auth_bundle,
    import_auth_bundle,
    get_data_dir,
)
from ai_runner.types import StructuredPlan, RunnerConfig
from ai_runner.auth.credentials import credential_store
from ai_runner.auth.oauth import oauth_manager
from ai_runner.harnesses.native import NativeHarness
from ai_runner.harnesses.agy import AgyHarness
from ai_runner.harnesses.opencode import OpenCodeHarness
from ai_runner.harnesses.pi import PiHarness

app = typer.Typer(
    name="ai-runner",
    help="Decentralized AI Issue Runner with Guarded Agentic Loop and multi-provider OAuth.",
    no_args_is_help=True
)
auth_app = typer.Typer(name="auth", help="Manage authentication and CI/CD secret export/import.")
app.add_typer(auth_app, name="auth")

console = Console()

@app.command()
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind"),
    port: int = typer.Option(4242, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development")
):
    """Start the decentralized runner daemon and embedded Web UI."""
    import uvicorn

    banner = Panel.fit(
        f"[bold green]⚡ AI Issue Runner Daemon Active[/bold green]\n\n"
        f"• Web Dashboard: [bold cyan]http://{host}:{port}[/bold cyan]\n"
        f"• OAuth Callback: [cyan]http://{host}:{port}/auth/callback[/cyan]\n"
        f"• Webhook Ingest: [cyan]http://{host}:{port}/api/webhook/github[/cyan]\n"
        f"• Data Directory: [dim]{get_data_dir()}[/dim]",
        border_style="blue"
    )
    console.print(banner)

    uvicorn.run("ai_runner.server.app:app", host=host, port=port, reload=reload)

@app.command()
def status():
    """Show runner status, authentication state, and configuration."""
    cfg = load_config()
    table = Table(title="AI Runner Status & Providers", border_style="blue")
    table.add_column("Provider", style="cyan", justify="left")
    table.add_column("Auth Mode", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")

    for p in ["google", "anthropic", "openai", "ollama"]:
        st = credential_store.get_status(p)
        status_text = "[bold green]Ready[/bold green]" if st.authenticated else "[yellow]Not Configured[/yellow]"
        detail = st.user_email or ("Present" if st.authenticated else "Missing")
        table.add_row(p.capitalize(), st.auth_mode.upper(), status_text, detail)

    console.print(table)
    console.print(f"\n[dim]Config file:[/dim] {get_data_dir() / 'config.yaml'}")

@app.command()
def run(
    plan_file: Optional[Path] = typer.Option(None, "--plan", "-f", help="Path to YAML or JSON plan file"),
    issue: Optional[str] = typer.Option(None, "--issue", "-i", help="GitHub issue URL or ID"),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w", help="Target project workspace directory"),
    harness: str = typer.Option("native", "--harness", help="Harness to use (native, agy, opencode, pi)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override (e.g. gemini-2.5-pro, claude-3-7-sonnet)")
):
    """Execute a structured plan with acceptance criteria verification."""
    if not plan_file and not issue:
        console.print("[bold red]Error:[/bold red] You must provide either --plan <file> or --issue <url>.")
        raise typer.Exit(code=1)

    if plan_file:
        if not plan_file.exists():
            console.print(f"[bold red]Error:[/bold red] Plan file {plan_file} not found.")
            raise typer.Exit(code=1)
        with open(plan_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        plan = StructuredPlan(**data)
    else:
        # Create minimal plan from issue
        from ai_runner.types import PlanPhase, AcceptanceCriterion
        plan = StructuredPlan(
            task_id=f"ISSUE-{issue.split('/')[-1]}",
            title=f"Resolve {issue}",
            summary=f"Automated resolution for {issue}",
            phases=[PlanPhase(id="p1", title="Resolve", description=f"Resolve {issue}")],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="tests",
                    description="Tests must pass",
                    command="pytest || npm test || cargo test",
                    expected_exit_code=0
                )
            ]
        )

    if model:
        plan.model = model
    plan.harness = harness

    console.print(f"[bold cyan]🚀 Executing Plan:[/bold cyan] {plan.title} [dim]({plan.task_id})[/dim]")
    console.print(f"[dim]Harness:[/dim] {harness} | [dim]Workspace:[/dim] {workspace.resolve()}")

    async def run_async():
        async def on_log(msg: str):
            console.print(msg)

        if harness == "agy":
            h = AgyHarness(workspace)
        elif harness == "opencode":
            h = OpenCodeHarness(workspace)
        elif harness == "pi":
            h = PiHarness(workspace)
        else:
            h = NativeHarness(workspace)

        return await h.run_plan(plan, on_log=on_log)

    success = asyncio.run(run_async())
    if success:
        console.print("[bold green]✅ Task completed and all acceptance criteria passed![/bold green]")
        raise typer.Exit(code=0)
    else:
        console.print("[bold red]❌ Task failed to satisfy acceptance criteria.[/bold red]")
        raise typer.Exit(code=1)

@auth_app.command("export")
def auth_export():
    """Export credentials bundle for GitHub Actions Secrets (AI_RUNNER_AUTH)."""
    bundle = export_auth_bundle()
    if not bundle or bundle == "e30=": # empty dict base64
        console.print("[yellow]Warning: No credentials currently saved to export.[/yellow]")
    console.print("\n[bold]Copy this secret value into GitHub Repository Secrets as AI_RUNNER_AUTH:[/bold]\n")
    console.print(f"[green]{bundle}[/green]\n")

@auth_app.command("import")
def auth_import(
    secret: str = typer.Argument(..., help="Base64 or JSON auth bundle to import")
):
    """Import credentials from a bundle string or CI secret."""
    try:
        creds = import_auth_bundle(secret)
        console.print(f"[bold green]✅ Successfully imported credentials for:[/bold green] {list(creds.keys())}")
    except Exception as e:
        console.print(f"[bold red]Import failed:[/bold red] {str(e)}")
        raise typer.Exit(code=1)

@app.command()
def login(
    provider: str = typer.Argument("google", help="Provider to login with (google, anthropic, openai)")
):
    """Log in to an AI provider interactively."""
    p = provider.lower()
    if p == "google":
        auth_url, state = oauth_manager.create_google_auth_url("http://127.0.0.1:4242/auth/callback")
        console.print("\n[bold]To complete Google Login, visit:[/bold]\n")
        console.print(f"[cyan underline]{auth_url}[/cyan underline]\n")
        console.print("[dim]Make sure 'ai-runner start' is running on port 4242 to receive the callback.[/dim]")
    elif p in ("anthropic", "openai"):
        key = typer.prompt(f"Enter {p.capitalize()} API Key", hide_input=True)
        credential_store.set_provider(p, {"api_key": key.strip(), "mode": "api_key"})
        console.print(f"[bold green]✅ Saved API key for {p.capitalize()}.[/bold green]")
    else:
        console.print(f"[bold red]Unknown provider:[/bold red] {provider}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
