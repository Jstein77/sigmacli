import tempfile
from pathlib import Path

import yaml

from sigma_sdlc.sync.file_utils import (
    find_model_file,
    get_model_filename,
    load_yaml_file,
    sanitize_filename,
    write_yaml_file,
)


def test_sanitize_filename_spaces():
    assert sanitize_filename("My Data Model") == "My_Data_Model"


def test_sanitize_filename_special_chars():
    assert sanitize_filename("Model (v2) / test") == "Model__v2____test"


def test_sanitize_filename_hyphens_preserved():
    assert sanitize_filename("my-model") == "my-model"


def test_get_model_filename():
    model = {"name": "Base Model", "dataModelId": "abc-123"}
    assert get_model_filename(model) == "Base_Model_abc-123.yaml"


def test_find_model_file_found(tmp_path):
    (tmp_path / "Foo_abc-123.yaml").write_text("test")
    result = find_model_file(tmp_path, "abc-123")
    assert result is not None
    assert result.name == "Foo_abc-123.yaml"


def test_find_model_file_not_found(tmp_path):
    assert find_model_file(tmp_path, "nonexistent") is None


def test_write_and_load_yaml(tmp_path):
    data = {"name": "Test", "version": 1, "items": ["a", "b"]}
    path = tmp_path / "test.yaml"
    write_yaml_file(path, data)
    loaded = load_yaml_file(path)
    assert loaded == data


def test_write_yaml_creates_parents(tmp_path):
    path = tmp_path / "sub" / "dir" / "test.yaml"
    write_yaml_file(path, {"key": "value"})
    assert path.exists()
    assert load_yaml_file(path) == {"key": "value"}
