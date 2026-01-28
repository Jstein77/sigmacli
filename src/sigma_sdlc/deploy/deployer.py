import logging
from pathlib import Path

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient
from sigma_sdlc.sync.file_utils import find_model_file, load_yaml_file, write_yaml_file

logger = logging.getLogger(__name__)

METADATA_KEYS = {
    "documentVersion",
    "latestDocumentVersion",
    "updatedAt",
    "createdAt",
    "ownerId",
    "createdBy",
    "updatedBy",
    "url",
}


def _content_fields(model: dict) -> dict:
    return {k: v for k, v in model.items() if k not in METADATA_KEYS}


def has_content_changes(local: dict, remote: dict) -> bool:
    return _content_fields(local) != _content_fields(remote)


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
            try:
                remote_spec = self.client.get_data_model_spec(model_id)
            except SigmaAPIError as e:
                if e.status_code == 404:
                    logger.warning("Model %s not found in Sigma, skipping", name)
                    results["skipped"].append({"name": name, "reason": "not found in Sigma"})
                    continue
                raise

            if not has_content_changes(local_data, remote_spec):
                logger.debug("Model %s is unchanged", name)
                results["unchanged"].append({"name": name})
                continue

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
                continue

            if dry_run:
                logger.info("Would push model %s", name)
                results["pushed"].append({"name": name})
                continue

            try:
                payload = _content_fields(local_data)
                payload.pop("dataModelId", None)
                response = self.client.update_data_model(model_id, payload)
                logger.info("Pushed model %s", name)
                results["pushed"].append({"name": name})
                self._update_local_version(model_id, local_data, response)
            except SigmaAPIError as e:
                logger.error("Failed to push model %s: %s", name, e)
                results["failed"].append({"name": name, "error": str(e)})

        return results

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
        for key in ("documentVersion", "latestDocumentVersion", "schemaVersion", "updatedAt"):
            if key in response:
                local_data[key] = response[key]

        path = find_model_file(self.data_models_dir, model_id)
        if path:
            write_yaml_file(path, local_data)
            logger.debug("Updated local version for %s", model_id)
