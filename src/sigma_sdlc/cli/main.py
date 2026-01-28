import click

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient
from sigma_sdlc.config.credentials import load_credentials


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


if __name__ == "__main__":
    cli()
