def needs_update(local: dict, remote: dict) -> bool:
    """Return True if remote has a newer version than local."""
    if remote.get("documentVersion", 0) != local.get("documentVersion", 0):
        return True
    if remote.get("schemaVersion", 0) != local.get("schemaVersion", 0):
        return True
    return False


def generate_diff_summary(changes: dict) -> str:
    """Format a summary like 'Synced N models (X new, Y updated, Z deleted)'."""
    new = len(changes.get("new", []))
    updated = len(changes.get("updated", []))
    deleted = len(changes.get("deleted", []))
    total = new + updated + deleted
    return f"Synced {total} models ({new} new, {updated} updated, {deleted} deleted)"
