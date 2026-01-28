from pathlib import Path
from unittest.mock import MagicMock, patch, call

import yaml

from sigma_sdlc.deploy.deployer import DeployManager, has_content_changes


def _make_model(model_id="m1", name="Test Model", doc_version=1, tables=None):
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
        client.get_data_model_spec.return_value = _make_model(tables=[{"id": "t2"}])
        client.update_data_model.return_value = {"documentVersion": 2}

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
        client.get_data_model_spec.return_value = _make_model(doc_version=5, tables=[{"id": "t2"}])
        client.update_data_model.return_value = {"documentVersion": 6}

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

        manager._update_local_version("m1", local, response)

        # Read the file back
        from sigma_sdlc.sync.file_utils import find_model_file, load_yaml_file
        path = find_model_file(manager.data_models_dir, "m1")
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
                        manager._update_local_version("m1", local, response)
                        mock_logger.warning.assert_called()
                        assert "Verification failed" in mock_logger.warning.call_args[0][0]

    def test_no_version_keys_in_response(self, tmp_path):
        local = _make_model()
        client, manager = _setup(tmp_path, local)

        with patch("sigma_sdlc.deploy.deployer.logger") as mock_logger:
            manager._update_local_version("m1", local, {"someOtherKey": "val"})
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
        client.get_data_model_spec.return_value = _make_model(tables=[{"id": "t2"}])
        client.update_data_model.return_value = {"documentVersion": 2}

        manager.deploy()

        assert mock_run.call_count == 3
        commands = [c[0][0] for c in mock_run.call_args_list]
        assert commands[0] == ["git", "add", "data-models/"]
        assert commands[1][0:2] == ["git", "commit"]
        assert commands[2] == ["git", "push"]
