import click

from pathlib import Path

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient
from sigma_sdlc.config.credentials import load_credentials
from sigma_sdlc.sync.syncer import SyncManager


@click.group()
@click.option("--profile", default="default", help="Credential profile to use")
@click.pass_context
def cli(ctx, profile):
    """Sigma SDLC - Manage Sigma data models with Git"""
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile


@cli.command()
@click.pass_context
def login(ctx):
    """Verify authentication with Sigma"""
    profile = ctx.obj["profile"]

    try:
        creds = load_credentials(profile)
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red")
        raise SystemExit(1)

    click.echo(f"Authenticating with profile '{profile}' at {creds.base_url}...")

    try:
        client = SigmaClient.authenticate(creds.base_url, creds.client_id, creds.client_secret)
    except SigmaAPIError as e:
        click.secho(f"Authentication failed: {e}", fg="red")
        raise SystemExit(1)
    except Exception as e:
        click.secho(f"Connection error: {e}", fg="red")
        raise SystemExit(1)

    click.secho("Successfully authenticated.", fg="green")
    ctx.obj["client"] = client


def _find_repo_root() -> Path:
    """Walk up from cwd to find .git directory."""
    current = Path.cwd()
    while True:
        if (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise click.ClickException("Not inside a git repository")
        current = parent


@cli.command()
@click.option("--workspace", default=None, help="Specific workspace ID to sync")
@click.option("--no-pr", is_flag=True, help="Skip PR creation")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
@click.pass_context
def sync(ctx, workspace, no_pr, dry_run):
    """Sync data models from Sigma to local YAML files."""
    profile = ctx.obj["profile"]

    try:
        creds = load_credentials(profile)
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red")
        raise SystemExit(1)

    click.echo(f"Authenticating with profile '{profile}'...")
    try:
        client = SigmaClient.authenticate(creds.base_url, creds.client_id, creds.client_secret)
    except SigmaAPIError as e:
        click.secho(f"Authentication failed: {e}", fg="red")
        raise SystemExit(1)
    except Exception as e:
        click.secho(f"Connection error: {e}", fg="red")
        raise SystemExit(1)

    repo_path = _find_repo_root()
    manager = SyncManager(client, repo_path)

    click.echo("Syncing data models from Sigma...")
    try:
        result = manager.sync(
            workspace_id=workspace,
            create_pr=not no_pr,
            dry_run=dry_run,
        )
    except Exception as e:
        click.secho(f"Sync failed: {e}", fg="red")
        raise SystemExit(1)

    for model in result.get("new", []):
        click.secho(f"  + {model['name']}", fg="green")
    for model in result.get("updated", []):
        click.secho(f"  ~ {model['name']}", fg="yellow")
    for model in result.get("deleted", []):
        click.secho(f"  - {model.get('name', model.get('dataModelId'))}", fg="red")

    click.echo(result.get("summary", ""))
    if "branch" in result:
        click.echo(f"Branch: {result['branch']}")


if __name__ == "__main__":
    cli()
