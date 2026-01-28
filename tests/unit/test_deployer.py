from pathlib import Path
from unittest.mock import MagicMock, patch, call

import yaml

from sigma_sdlc.deploy.deployer import DeployManager, has_content_changes, _content_fields


def _make_model(model_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890", name="Test Model", doc_version=1, tables=None):
    return {
        "dataModelId": model_id,
        "name": name,
        "documentVersion": doc_version,
        "tables": tables or [{"id": "t1"}],
    }


def _write_model(data_dir: Path, model: dict):
    from sigma_sdlc.sync.file_utils import get_model_filename, write_yaml_file
    write_yaml_file(data_dir / get_model_filename(model), model)


def _setup(tmp_path, local_model):
    data_dir = tmp_path / "data-models"
    data_dir.mkdir()
    _write_model(data_dir, local_model)
    client = MagicMock()
    manager = DeployManager(client, tmp_path)
    return client, manager


class TestDeployPush:
    def test_deploy_pushes_changed_model(self, tmp_path):
        local = _make_model(tables=[{"id": "t1"}])
        client, manager = _setup(tmp_path, local)
        remote = _make_model(tables=[{"id": "t2"}])
        refreshed = {**remote, "documentVersion": 2, "updatedAt": "2025-01-01"}
        client.get_data_model_spec.side_effect = [remote, refreshed]
        client.update_data_model.return_value = {}

        with patch.object(manager, "_auto_commit_and_push"):
            result = manager.deploy()

        assert len(result["pushed"]) == 1
        client.update_data_model.assert_called_once()

    def test_deploy_skips_unchanged_model(self, tmp_path):
        local = _make_model()
        client, manager = _setup(tmp_path, local)
        client.get_data_model_spec.return_value = _make_model()

        result = manager.deploy()

        assert len(result["unchanged"]) == 1
        client.update_data_model.assert_not_called()

    def test_deploy_skips_version_conflict(self, tmp_path):
        local = _make_model(doc_version=1, tables=[{"id": "t1"}])
        client, manager = _setup(tmp_path, local)
        client.get_data_model_spec.return_value = _make_model(doc_version=5, tables=[{"id": "t2"}])

        result = manager.deploy()

        assert len(result["skipped"]) == 1
        assert "remote version" in result["skipped"][0]["reason"]
        client.update_data_model.assert_not_called()

    def test_deploy_force_overrides_version_conflict(self, tmp_path):
        local = _make_model(doc_version=1, tables=[{"id": "t1"}])
        client, manager = _setup(tmp_path, local)
        remote = _make_model(doc_version=5, tables=[{"id": "t2"}])
        refreshed = {**remote, "documentVersion": 6}
        client.get_data_model_spec.side_effect = [remote, refreshed]
        client.update_data_model.return_value = {}

        with patch.object(manager, "_auto_commit_and_push"):
            result = manager.deploy(force=True)

        assert len(result["pushed"]) == 1
        client.update_data_model.assert_called_once()

    def test_deploy_dry_run_no_side_effects(self, tmp_path):
        local = _make_model(tables=[{"id": "t1"}])
        client, manager = _setup(tmp_path, local)
        client.get_data_model_spec.return_value = _make_model(tables=[{"id": "t2"}])

        result = manager.deploy(dry_run=True)

        assert len(result["pushed"]) == 1
        client.update_data_model.assert_not_called()


class TestUpdateLocalVersion:
    def test_writes_back_version(self, tmp_path):
        local = _make_model()
        client, manager = _setup(tmp_path, local)
        response = {"documentVersion": 2, "updatedAt": "2025-01-01"}

        manager._update_local_version("a1b2c3d4-e5f6-7890-abcd-ef1234567890", local, response)

        # Read the file back
        from sigma_sdlc.sync.file_utils import find_model_file, load_yaml_file
        path = find_model_file(manager.data_models_dir, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        written = load_yaml_file(path)
        assert written["documentVersion"] == 2
        assert written["updatedAt"] == "2025-01-01"

    def test_verification_catches_corruption(self, tmp_path):
        local = _make_model()
        client, manager = _setup(tmp_path, local)
        response = {"documentVersion": 2}

        with patch("sigma_sdlc.deploy.deployer.load_yaml_file", return_value={"documentVersion": 999}):
            with patch("sigma_sdlc.deploy.deployer.write_yaml_file"):
                with patch("sigma_sdlc.deploy.deployer.find_model_file", return_value=Path("fake")):
                    with patch("sigma_sdlc.deploy.deployer.logger") as mock_logger:
                        manager._update_local_version("a1b2c3d4-e5f6-7890-abcd-ef1234567890", local, response)
                        mock_logger.warning.assert_called()
                        assert "Verification failed" in mock_logger.warning.call_args[0][0]

    def test_no_version_keys_in_response(self, tmp_path):
        local = _make_model()
        client, manager = _setup(tmp_path, local)

        with patch("sigma_sdlc.deploy.deployer.logger") as mock_logger:
            manager._update_local_version("a1b2c3d4-e5f6-7890-abcd-ef1234567890", local, {"someOtherKey": "val"})
            mock_logger.warning.assert_called()
            assert "no version keys" in mock_logger.warning.call_args[0][0]

    def test_file_not_found_logs_warning(self, tmp_path):
        client = MagicMock()
        manager = DeployManager(client, tmp_path)
        # No data-models dir, so find_model_file returns None
        (tmp_path / "data-models").mkdir()

        with patch("sigma_sdlc.deploy.deployer.logger") as mock_logger:
            manager._update_local_version("nonexistent", {}, {"documentVersion": 2})
            mock_logger.warning.assert_called()
            assert "not found" in mock_logger.warning.call_args[0][0]


class TestAutoCommitAndPush:
    @patch("sigma_sdlc.deploy.deployer.subprocess.run")
    def test_deploy_auto_commits_after_push(self, mock_run, tmp_path):
        local = _make_model(tables=[{"id": "t1"}])
        client, manager = _setup(tmp_path, local)
        remote = _make_model(tables=[{"id": "t2"}])
        refreshed = {**remote, "documentVersion": 2}
        client.get_data_model_spec.side_effect = [remote, refreshed]
        client.update_data_model.return_value = {}

        manager.deploy()

        assert mock_run.call_count == 3
        commands = [c[0][0] for c in mock_run.call_args_list]
        assert commands[0] == ["git", "add", "data-models/"]
        assert commands[1][0:2] == ["git", "commit"]
        assert commands[2] == ["git", "push"]


class TestContentChangesMetadata:
    def test_extra_metadata_fields_ignored_in_comparison(self, tmp_path):
        """Regression: models with extra metadata like folderId/schemaVersion
        should not be seen as changed when remote lacks those fields."""
        local = {
            **_make_model(),
            "schemaVersion": 3,
            "folderId": "folder-abc",
        }
        remote = _make_model()
        assert not has_content_changes(local, remote)

    def test_dataModelId_ignored_in_comparison(self):
        local = _make_model(model_id="aaaa-bbbb")
        remote = _make_model(model_id="cccc-dddd")
        # Only differs by dataModelId which is metadata
        assert not has_content_changes(local, remote)


class TestDeployNewModel:
    def test_deploy_creates_and_refreshes_new_model(self, tmp_path):
        data_dir = tmp_path / "data-models"
        data_dir.mkdir()

        local = {
            "dataModelId": "My_New_Model",
            "name": "My New Model",
            "tables": [{"id": "t1"}],
        }
        from sigma_sdlc.sync.file_utils import get_model_filename, write_yaml_file
        write_yaml_file(data_dir / get_model_filename(local), local)

        client = MagicMock()
        manager = DeployManager(client, tmp_path)

        new_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        client.create_data_model.return_value = {
            "dataModelId": new_uuid,
            "name": "My New Model",
            "documentVersion": 1,
        }
        client.get_data_model_spec.return_value = {
            "dataModelId": new_uuid,
            "name": "My New Model",
            "documentVersion": 1,
            "latestDocumentVersion": 1,
            "updatedAt": "2025-06-01T00:00:00Z",
            "tables": [{"id": "t1"}],
        }

        with patch.object(manager, "_auto_commit_and_push"):
            result = manager.deploy()

        # Model was pushed
        assert len(result["pushed"]) == 1
        assert result["pushed"][0]["name"] == "My New Model"

        # create called once, without placeholder ID in payload
        client.create_data_model.assert_called_once()
        payload = client.create_data_model.call_args[0][0]
        assert "dataModelId" not in payload

        # get_data_model_spec called once with the new UUID
        client.get_data_model_spec.assert_called_once_with(new_uuid)

        # Verify written YAML file has UUID-based filename and correct content
        new_file = data_dir / get_model_filename({"dataModelId": new_uuid, "name": "My New Model"})
        assert new_file.exists()
        from sigma_sdlc.sync.file_utils import load_yaml_file
        written = load_yaml_file(new_file)
        assert written["dataModelId"] == new_uuid
        assert written["documentVersion"] == 1
        assert written["latestDocumentVersion"] == 1

        # Old placeholder file removed
        old_file = data_dir / get_model_filename(local)
        assert not old_file.exists() or old_file == new_file


class TestContentFieldsStripsSuccess:
    def test_success_field_excluded_from_content(self):
        """Regression: 'success' response envelope field must not appear in deploy payload."""
        model = {**_make_model(), "success": True}
        content = _content_fields(model)
        assert "success" not in content
