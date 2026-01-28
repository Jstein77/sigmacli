import logging
import subprocess
from datetime import datetime
from pathlib import Path

from git import Repo

from sigma_sdlc.client.sigma_client import SigmaClient
from sigma_sdlc.sync.diff import generate_diff_summary, needs_update
from sigma_sdlc.sync.file_utils import (
    find_model_file,
    get_model_filename,
    load_yaml_file,
    write_yaml_file,
)

logger = logging.getLogger(__name__)


class SyncManager:
    def __init__(self, client: SigmaClient, repo_path: Path):
        self.client = client
        self.repo_path = repo_path
        self.data_models_dir = repo_path / "data-models"

    def sync(self, workspace_id: str | None = None, create_pr: bool = True, dry_run: bool = False) -> dict:
        # Fetch remote models
        remote_models = self._fetch_remote_models()

        # Index local models by ID
        local_index = self._index_local_models()

        # Compute changes
        remote_ids = set()
        changes = {"new": [], "updated": [], "deleted": [], "unchanged": []}

        for model in remote_models:
            mid = model["dataModelId"]
            remote_ids.add(mid)

            if mid not in local_index:
                changes["new"].append(model)
            elif needs_update(local_index[mid], model):
                changes["updated"].append(model)
            else:
                changes["unchanged"].append(model)

        for mid, local_data in local_index.items():
            if mid not in remote_ids:
                changes["deleted"].append(local_data)

        if dry_run:
            changes["summary"] = generate_diff_summary(changes)
            return changes

        # Apply changes on a new branch
        repo = Repo(self.repo_path)
        branch_name = f"sigma-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        repo.git.checkout("-b", branch_name)

        try:
            self._apply_changes(changes)
            self._commit(repo, changes)

            if create_pr:
                self._create_pr(branch_name, changes)
        except Exception:
            repo.git.checkout("main")
            repo.git.branch("-D", branch_name)
            raise

        changes["summary"] = generate_diff_summary(changes)
        changes["branch"] = branch_name
        return changes

    def _fetch_remote_models(self) -> list:
        model_list = self.client.get_data_models()

        models = []
        for entry in model_list:
            full = self.client.get_data_model(entry["dataModelId"])
            models.append(full)
        return models

    def _index_local_models(self) -> dict:
        index = {}
        if not self.data_models_dir.exists():
            return index
        for path in self.data_models_dir.glob("*.yaml"):
            data = load_yaml_file(path)
            mid = data.get("dataModelId")
            if mid:
                index[mid] = data
        return index

    def _apply_changes(self, changes: dict) -> None:
        self.data_models_dir.mkdir(parents=True, exist_ok=True)

        for model in changes["new"] + changes["updated"]:
            filename = get_model_filename(model)
            # If updated, remove old file (name may have changed)
            old = find_model_file(self.data_models_dir, model["dataModelId"])
            if old and old.name != filename:
                old.unlink()
            write_yaml_file(self.data_models_dir / filename, model)

        for model in changes["deleted"]:
            path = find_model_file(self.data_models_dir, model["dataModelId"])
            if path:
                path.unlink()

    def _commit(self, repo: Repo, changes: dict) -> None:
        repo.git.add("data-models/")
        if repo.is_dirty(index=True):
            summary = generate_diff_summary(changes)
            repo.git.commit("-m", f"Sigma sync: {summary}")

    def _create_pr(self, branch_name: str, changes: dict) -> str | None:
        summary = generate_diff_summary(changes)
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", f"Sigma sync: {summary}",
                    "--body", f"Automated sync from Sigma API.\n\n{summary}",
                ],
                capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning("Could not create PR: %s", e)
            return None
