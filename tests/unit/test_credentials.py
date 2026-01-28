import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from sigma_sdlc.config.credentials import SigmaCredentials, load_credentials


@pytest.fixture
def creds_yaml():
    return {
        "profiles": {
            "default": {
                "base_url": "https://api.example.com",
                "client_id": "test-id",
                "client_secret": "test-secret",
            },
            "staging": {
                "base_url": "https://api.staging.example.com",
                "client_id": "staging-id",
                "client_secret": "staging-secret",
            },
        }
    }


class TestLoadFromEnvVars:
    def test_loads_from_env(self):
        env = {
            "SIGMA_CLIENT_ID": "env-id",
            "SIGMA_CLIENT_SECRET": "env-secret",
            "SIGMA_BASE_URL": "https://env.example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            creds = load_credentials()
        assert creds.client_id == "env-id"
        assert creds.client_secret == "env-secret"
        assert creds.base_url == "https://env.example.com"

    def test_env_uses_default_base_url(self):
        env = {"SIGMA_CLIENT_ID": "id", "SIGMA_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, env, clear=False):
            creds = load_credentials()
        assert "sigmacomputing" in creds.base_url

    def test_env_takes_priority_over_file(self, tmp_path, creds_yaml):
        creds_file = tmp_path / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(creds_yaml))

        env = {"SIGMA_CLIENT_ID": "env-id", "SIGMA_CLIENT_SECRET": "env-secret"}
        with patch.dict(os.environ, env, clear=False), patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path):
            creds = load_credentials()
        assert creds.client_id == "env-id"


class TestLoadFromFile:
    def test_loads_from_project_file(self, tmp_path, creds_yaml):
        creds_file = tmp_path / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(creds_yaml))

        env = {}
        with patch.dict(os.environ, env, clear=True), patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path):
            # Also patch home to avoid picking up real home creds
            with patch("sigma_sdlc.config.credentials.Path.home", return_value=tmp_path / "fakehome"):
                creds = load_credentials()
        assert creds.client_id == "test-id"
        assert creds.base_url == "https://api.example.com"

    def test_loads_from_home_file(self, tmp_path, creds_yaml):
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        creds_file = home_dir / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(creds_yaml))

        with patch.dict(os.environ, {}, clear=True), \
             patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path / "noproject"), \
             patch("sigma_sdlc.config.credentials.Path.home", return_value=home_dir):
            creds = load_credentials()
        assert creds.client_id == "test-id"

    def test_profile_switching(self, tmp_path, creds_yaml):
        creds_file = tmp_path / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(creds_yaml))

        with patch.dict(os.environ, {}, clear=True), \
             patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path), \
             patch("sigma_sdlc.config.credentials.Path.home", return_value=tmp_path / "fakehome"):
            creds = load_credentials("staging")
        assert creds.client_id == "staging-id"
        assert creds.base_url == "https://api.staging.example.com"


class TestValidationErrors:
    def test_no_credentials_found(self, tmp_path):
        with patch.dict(os.environ, {}, clear=True), \
             patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path), \
             patch("sigma_sdlc.config.credentials.Path.home", return_value=tmp_path):
            with pytest.raises(ValueError, match="No credentials found"):
                load_credentials()

    def test_missing_profile(self, tmp_path, creds_yaml):
        creds_file = tmp_path / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(creds_yaml))

        with patch.dict(os.environ, {}, clear=True), \
             patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path), \
             patch("sigma_sdlc.config.credentials.Path.home", return_value=tmp_path / "fakehome"):
            with pytest.raises(ValueError, match="No credentials found"):
                load_credentials("nonexistent")

    def test_missing_fields(self, tmp_path):
        bad_yaml = {"profiles": {"default": {"base_url": "https://example.com"}}}
        creds_file = tmp_path / ".sigma" / "credentials.yml"
        creds_file.parent.mkdir()
        creds_file.write_text(yaml.dump(bad_yaml))

        with patch.dict(os.environ, {}, clear=True), \
             patch("sigma_sdlc.config.credentials.Path.cwd", return_value=tmp_path), \
             patch("sigma_sdlc.config.credentials.Path.home", return_value=tmp_path / "fakehome"):
            with pytest.raises(ValueError, match="missing required fields"):
                load_credentials()
