import re
from pathlib import Path

import yaml


def sanitize_filename(name: str) -> str:
    """Replace non-word chars (except hyphens) with underscores."""
    return re.sub(r"[^\w\-]", "_", name)


def get_model_filename(model: dict) -> str:
    """Return filename like {Sanitized_Name}_{dataModelId}.yaml."""
    name = sanitize_filename(model["name"])
    return f"{name}_{model['dataModelId']}.yaml"


def find_model_file(data_models_dir: Path, model_id: str) -> Path | None:
    """Find an existing YAML file for the given model ID."""
    matches = list(data_models_dir.glob(f"*_{model_id}.yaml"))
    return matches[0] if matches else None


def load_yaml_file(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_yaml_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
