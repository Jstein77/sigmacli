import click

from pathlib import Path

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient
from sigma_sdlc.config.credentials import load_credentials
from sigma_sdlc.deploy.deployer import DeployManager
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


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be pushed without executing")
@click.option("--force", is_flag=True, help="Push even if remote version is newer")
@click.pass_context
def deploy(ctx, dry_run, force):
    """Push local data model changes to Sigma."""
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
    manager = DeployManager(client, repo_path)

    click.echo("Deploying local changes to Sigma...")
    try:
        result = manager.deploy(dry_run=dry_run, force=force)
    except Exception as e:
        click.secho(f"Deploy failed: {e}", fg="red")
        raise SystemExit(1)

    for model in result.get("pushed", []):
        click.secho(f"  ↑ {model['name']}", fg="green")
    for model in result.get("skipped", []):
        click.secho(f"  ⊘ {model['name']}: {model.get('reason', '')}", fg="yellow")
    for model in result.get("failed", []):
        click.secho(f"  ✗ {model['name']}: {model.get('error', '')}", fg="red")

    pushed = len(result.get("pushed", []))
    skipped = len(result.get("skipped", []))
    failed = len(result.get("failed", []))
    unchanged = len(result.get("unchanged", []))
    click.echo(f"Deploy complete: {pushed} pushed, {unchanged} unchanged, {skipped} skipped, {failed} failed")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
