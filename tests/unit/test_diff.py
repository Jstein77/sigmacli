from sigma_sdlc.sync.diff import generate_diff_summary, needs_update


def test_needs_update_same_versions():
    local = {"documentVersion": 5, "schemaVersion": 1}
    remote = {"documentVersion": 5, "schemaVersion": 1}
    assert needs_update(local, remote) is False


def test_needs_update_doc_version_changed():
    local = {"documentVersion": 5, "schemaVersion": 1}
    remote = {"documentVersion": 6, "schemaVersion": 1}
    assert needs_update(local, remote) is True


def test_needs_update_schema_version_changed():
    local = {"documentVersion": 5, "schemaVersion": 1}
    remote = {"documentVersion": 5, "schemaVersion": 2}
    assert needs_update(local, remote) is True


def test_needs_update_missing_fields():
    assert needs_update({}, {"documentVersion": 1}) is True
    assert needs_update({}, {}) is False


def test_generate_diff_summary():
    changes = {
        "new": [1, 2],
        "updated": [3],
        "deleted": [4, 5, 6],
    }
    assert generate_diff_summary(changes) == "Synced 6 models (2 new, 1 updated, 3 deleted)"


def test_generate_diff_summary_empty():
    assert generate_diff_summary({}) == "Synced 0 models (0 new, 0 updated, 0 deleted)"
