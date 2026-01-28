import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SigmaCredentials:
    base_url: str
    client_id: str
    client_secret: str


def _find_project_root() -> Path | None:
    """Walk up from cwd looking for a directory containing .sigma/credentials.yml."""
    current = Path.cwd()
    while True:
        if (current / ".sigma" / "credentials.yml").is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_credentials(profile: str = "default") -> SigmaCredentials:
    """Load credentials in priority order: env vars, project file, home dir."""
    # 1. Environment variables
    client_id = os.environ.get("SIGMA_CLIENT_ID")
    client_secret = os.environ.get("SIGMA_CLIENT_SECRET")
    base_url = os.environ.get(
        "SIGMA_BASE_URL", "https://api.staging.us.aws.sigmacomputing.io"
    )

    if client_id and client_secret:
        return SigmaCredentials(
            base_url=base_url, client_id=client_id, client_secret=client_secret
        )

    # 2. Project-level .sigma/credentials.yml (search upward from cwd)
    project_root = _find_project_root()
    if project_root:
        result = _load_from_file(project_root / ".sigma" / "credentials.yml", profile)
        if result:
            return result

    # 3. Home directory ~/.sigma/credentials.yml
    home_creds = Path.home() / ".sigma" / "credentials.yml"
    result = _load_from_file(home_creds, profile)
    if result:
        return result

    raise ValueError(
        f"No credentials found for profile '{profile}'. "
        "Set SIGMA_CLIENT_ID and SIGMA_CLIENT_SECRET environment variables, "
        "or create a credentials file at .sigma/credentials.yml or ~/.sigma/credentials.yml"
    )


def _load_from_file(path: Path, profile: str) -> SigmaCredentials | None:
    """Load credentials from a YAML file for the given profile."""
    if not path.is_file():
        return None

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "profiles" not in data:
        return None

    profiles = data["profiles"]
    if profile not in profiles:
        return None

    p = profiles[profile]
    missing = [k for k in ("base_url", "client_id", "client_secret") if k not in p]
    if missing:
        raise ValueError(
            f"Profile '{profile}' in {path} is missing required fields: {', '.join(missing)}"
        )

    return SigmaCredentials(
        base_url=p["base_url"],
        client_id=p["client_id"],
        client_secret=p["client_secret"],
    )
