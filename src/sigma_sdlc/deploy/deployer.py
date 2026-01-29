import logging
import re
import subprocess
from pathlib import Path

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient
from sigma_sdlc.sync.file_utils import (
    find_model_file,
    get_model_filename,
    load_yaml_file,
    write_yaml_file,
)

logger = logging.getLogger(__name__)

METADATA_KEYS = {
    "success",
}


def _content_fields(model: dict) -> dict:
    return {k: v for k, v in model.items() if k not in METADATA_KEYS}


def has_content_changes(local: dict, remote: dict) -> bool:
    # if _content_fields(local) != _content_fields(remote):
    #     print(_content_fields(local))
    #     print(_content_fields(remote))
    #     return print("Content changes")
    return _content_fields(local) != _content_fields(remote)


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _is_new_model(model_id: str) -> bool:
    return not _UUID_RE.match(model_id)


class DeployManager:
    def __init__(self, client: SigmaClient, repo_path: Path):
        self.client = client
        self.repo_path = repo_path
        self.data_models_dir = repo_path / "data-models"

    def deploy(self, dry_run: bool = False, force: bool = False) -> dict:
        results = {"pushed": [], "skipped": [], "failed": [], "unchanged": []}

        local_models = self._load_local_models()
        if not local_models:
            logger.info("No local data models found")
            return results

        for model_id, local_data in local_models.items():
            name = local_data.get("name", model_id)

            if _is_new_model(model_id):
                self._deploy_new_model(name, model_id, local_data, results, dry_run)
            else:
                self._deploy_existing_model(name, model_id, local_data, results, dry_run, force)

        if results["pushed"] and not dry_run:
            self._auto_commit_and_push()

        return results

    def _deploy_new_model(self, name, model_id, local_data, results, dry_run):
        if dry_run:
            logger.info("Would create new model %s", name)
            results["pushed"].append({"name": name})
            return

        try:
            payload = _content_fields(local_data)
            payload.pop("dataModelId", None)
            response = self.client.create_data_model(payload)
            new_id = response.get("dataModelId")
            if not new_id:
                logger.error("Create response for %s missing dataModelId", name)
                results["failed"].append({"name": name, "error": "no dataModelId in response"})
                return

            logger.info("Created model %s with id %s", name, new_id)

            # Re-fetch full spec to get complete metadata (e.g. latestDocumentVersion)
            refreshed = self.client.get_data_model_spec(new_id)
            response.update(refreshed)

            # Update local data with real ID and all metadata from response
            local_data["dataModelId"] = new_id
            ## Replace all keys in local yaml with sigma generted keys
            for key, value in response.items():
                print(key, value)    
                local_data[key] = value

            new_filename = get_model_filename(local_data)
            new_path = self.data_models_dir / new_filename
            write_yaml_file(new_path, local_data)

            # Remove old file
            old_path = find_model_file(self.data_models_dir, model_id)
            if old_path and old_path != new_path:
                old_path.unlink()
            elif not old_path:
                # Find by scanning all files for the old model_id value
                for p in self.data_models_dir.glob("*.yaml"):
                    d = load_yaml_file(p)
                    if d.get("dataModelId") == model_id and p != new_path:
                        p.unlink()
                        break

            results["pushed"].append({"name": name})
        except SigmaAPIError as e:
            logger.error("Failed to create model %s: %s", name, e)
            results["failed"].append({"name": name, "error": str(e)})

    def _deploy_existing_model(self, name, model_id, local_data, results, dry_run, force):
        try:
            remote_spec = self.client.get_data_model_spec(model_id)
        except SigmaAPIError as e:
            if e.status_code == 404:
                logger.warning("Model %s not found in Sigma, skipping", name)
                results["skipped"].append({"name": name, "reason": "not found in Sigma"})
                return
            raise

        if not has_content_changes(local_data, remote_spec):
            logger.debug("Model %s is unchanged", name)
            results["unchanged"].append({"name": name})
            return

        remote_version = remote_spec.get("documentVersion", 0)
        local_version = local_data.get("documentVersion", 0)
        if remote_version > local_version and not force:
            logger.warning(
                "Model %s: remote version %d > local %d, skipping (use --force to override)",
                name, remote_version, local_version,
            )
            results["skipped"].append({
                "name": name,
                "reason": f"remote version {remote_version} > local {local_version}",
            })
            return

        if dry_run:
            logger.info("Would push model %s", name)
            results["pushed"].append({"name": name})
            return

        try:
            payload = _content_fields(local_data)
            payload.pop("dataModelId", None)
            response = self.client.update_data_model(model_id, payload)
            # Re-fetch spec to get updated version metadata
            refreshed = self.client.get_data_model_spec(model_id)
            response.update(refreshed)
            logger.info("Pushed model %s", name)
            results["pushed"].append({"name": name})
            self._update_local_version(model_id, local_data, response)
        except SigmaAPIError as e:
            logger.error("Failed to push model %s: %s", name, e)
            results["failed"].append({"name": name, "error": str(e)})

    def _load_local_models(self) -> dict:
        index = {}
        if not self.data_models_dir.exists():
            return index
        for path in self.data_models_dir.glob("*.yaml"):
            data = load_yaml_file(path)
            mid = data.get("dataModelId")
            if mid:
                index[mid] = data
        return index

    def _update_local_version(self, model_id: str, local_data: dict, response: dict) -> None:
        version_keys = ("documentVersion", "latestDocumentVersion", "schemaVersion", "updatedAt")
        updated_keys = [k for k in version_keys if k in response]
        if not updated_keys:
            logger.warning("API response for %s contains no version keys", model_id)
            return

        for key in updated_keys:
            local_data[key] = response[key]

        path = find_model_file(self.data_models_dir, model_id)
        if not path:
            logger.warning("Local file not found for model %s, cannot update version", model_id)
            return

        write_yaml_file(path, local_data)

        # Read back and verify
        written = load_yaml_file(path)
        for key in updated_keys:
            if written.get(key) != local_data[key]:
                logger.warning(
                    "Verification failed for %s: key %s expected %r, got %r",
                    model_id, key, local_data[key], written.get(key),
                )
                return

        logger.debug("Updated local version for %s", model_id)

    def _auto_commit_and_push(self) -> None:
        try:
            subprocess.run(
                ["git", "add", "data-models/"],
                cwd=self.repo_path, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Post-deploy: Update document versions"],
                cwd=self.repo_path, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "push"],
                cwd=self.repo_path, check=True, capture_output=True,
            )
            logger.info("Auto-committed and pushed version updates")
        except subprocess.CalledProcessError as e:
            logger.error("Git auto-commit/push failed: %s", e.stderr.decode() if e.stderr else e)
