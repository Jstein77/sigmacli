from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from sigma_sdlc.sync.syncer import SyncManager


def _make_model(model_id, name="Test Model", doc_version=1, schema_version=1):
    return {
        "dataModelId": model_id,
        "name": name,
        "documentVersion": doc_version,
        "schemaVersion": schema_version,
    }


def _write_local_model(data_models_dir, model):
    from sigma_sdlc.sync.file_utils import get_model_filename, write_yaml_file
    write_yaml_file(data_models_dir / get_model_filename(model), model)


class TestSyncManagerDryRun:
    def test_new_model_detected(self, tmp_path):
        client = MagicMock()
        client.get_workspaces.return_value = [{"workspaceId": "ws1"}]
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model.return_value = _make_model("m1")
        client.get_data_model_spec.return_value = {"tables": []}

        manager = SyncManager(client, tmp_path)
        result = manager.sync(dry_run=True)

        assert len(result["new"]) == 1
        assert result["new"][0]["dataModelId"] == "m1"
        assert len(result["updated"]) == 0
        assert len(result["deleted"]) == 0

    def test_updated_model_detected(self, tmp_path):
        data_dir = tmp_path / "data-models"
        data_dir.mkdir()
        local = _make_model("m1", doc_version=1)
        _write_local_model(data_dir, local)

        remote = _make_model("m1", doc_version=2)
        client = MagicMock()
        client.get_workspaces.return_value = [{"workspaceId": "ws1"}]
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model.return_value = remote
        client.get_data_model_spec.return_value = {"tables": []}

        manager = SyncManager(client, tmp_path)
        result = manager.sync(dry_run=True)

        assert len(result["updated"]) == 1
        assert len(result["new"]) == 0

    def test_deleted_model_detected(self, tmp_path):
        data_dir = tmp_path / "data-models"
        data_dir.mkdir()
        local = _make_model("m1")
        _write_local_model(data_dir, local)

        client = MagicMock()
        client.get_workspaces.return_value = [{"workspaceId": "ws1"}]
        client.get_data_models.return_value = []

        manager = SyncManager(client, tmp_path)
        result = manager.sync(dry_run=True)

        assert len(result["deleted"]) == 1
        assert len(result["new"]) == 0

    def test_unchanged_model(self, tmp_path):
        data_dir = tmp_path / "data-models"
        data_dir.mkdir()
        model = _make_model("m1", doc_version=5, schema_version=2)
        _write_local_model(data_dir, model)

        client = MagicMock()
        client.get_workspaces.return_value = [{"workspaceId": "ws1"}]
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model.return_value = _make_model("m1", doc_version=5, schema_version=2)
        client.get_data_model_spec.return_value = {"tables": []}

        manager = SyncManager(client, tmp_path)
        result = manager.sync(dry_run=True)

        assert len(result["unchanged"]) == 1
        assert len(result["new"]) == 0
        assert len(result["updated"]) == 0
        assert len(result["deleted"]) == 0

    def test_workspace_filter(self, tmp_path):
        client = MagicMock()
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model.return_value = _make_model("m1")
        client.get_data_model_spec.return_value = {"tables": []}

        manager = SyncManager(client, tmp_path)
        result = manager.sync(dry_run=True)

        client.get_data_models.assert_called_once_with()

    def test_dry_run_does_not_write_files(self, tmp_path):
        client = MagicMock()
        client.get_workspaces.return_value = [{"workspaceId": "ws1"}]
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model.return_value = _make_model("m1")
        client.get_data_model_spec.return_value = {"tables": []}

        manager = SyncManager(client, tmp_path)
        manager.sync(dry_run=True)

        assert not (tmp_path / "data-models").exists() or \
            len(list((tmp_path / "data-models").glob("*.yaml"))) == 0


class TestSyncManagerGitOps:
    def test_no_commit_skips_push_and_pr(self, tmp_path):
        """When applied changes produce no git diff (file identical to main), skip push/PR."""
        data_dir = tmp_path / "data-models"
        data_dir.mkdir()
        # Pre-populate local with the same model that remote will return
        model = _make_model("m1", doc_version=1, schema_version=1)
        _write_local_model(data_dir, model)

        client = MagicMock()
        client.get_data_models.return_value = [{"dataModelId": "m1"}]
        client.get_data_model_spec.return_value = model

        mock_repo = MagicMock()
        mock_repo.is_dirty.return_value = False  # No actual git changes

        with patch("sigma_sdlc.sync.syncer.Repo", return_value=mock_repo):
            manager = SyncManager(client, tmp_path)
            # Remove local file to trigger "new" detection
            for f in data_dir.glob("*.yaml"):
                f.unlink()

            result = manager.sync(create_pr=True)

        # Should clean up branch, not attempt push or PR
        mock_repo.git.checkout.assert_any_call("main")
        mock_repo.git.push.assert_not_called()
        assert "branch" not in result
