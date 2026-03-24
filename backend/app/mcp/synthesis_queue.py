"""In-memory synthesis queue for feature cluster processing.

Tracks pending code clusters awaiting feature synthesis by Claude Code.
Shared between the scan pipeline (producer) and MCP handlers (consumer).
"""

# Pending clusters for feature synthesis, keyed by queue_key (str).
# queue_key is "org_id" for single-repo or "org_id:repo_name" for parallel.
# Set by scan pipeline before calling Claude Code, consumed by MCP tools.
_synthesis_queue: dict[str, list[dict]] = {}

# Maps org_id → list of active queue keys (for parallel repo support).
# When get_pending_features is called with just org_id, it checks all
# active queues for that org and returns from the first non-empty one.
_active_queue_keys: dict[str, list[str]] = {}


def set_synthesis_queue(
    org_id: str,
    clusters: list[dict],
    *,
    repo_name: str | None = None,
) -> str:
    """Populate the synthesis queue with clusters to process.

    Returns:
        The queue key used (for passing to clear_synthesis_queue).
    """
    queue_key = f"{org_id}:{repo_name}" if repo_name else org_id
    _synthesis_queue[queue_key] = clusters
    _active_queue_keys.setdefault(org_id, [])
    if queue_key not in _active_queue_keys[org_id]:
        _active_queue_keys[org_id].append(queue_key)
    return queue_key


def remove_from_queue(org_id: str, cluster_names: list[str]) -> None:
    """Remove processed clusters from all active queues for the org."""
    names_set = set(cluster_names)
    for key in _active_queue_keys.get(org_id, []):
        if key in _synthesis_queue:
            _synthesis_queue[key] = [
                c for c in _synthesis_queue[key] if c["name"] not in names_set
            ]


def get_queue_remaining(org_id: str, *, queue_key: str | None = None) -> list[dict]:
    """Return clusters still pending synthesis.

    If queue_key is given, return from that specific queue.
    Otherwise, aggregate remaining from all active queues for the org.
    """
    if queue_key:
        return _synthesis_queue.get(queue_key, [])
    remaining: list[dict] = []
    for key in _active_queue_keys.get(org_id, []):
        remaining.extend(_synthesis_queue.get(key, []))
    return remaining


def clear_synthesis_queue(org_id: str, *, queue_key: str | None = None) -> None:
    """Remove entries after synthesis completes.

    If queue_key is given, clear only that queue. Otherwise clear all for the org.
    """
    if queue_key:
        _synthesis_queue.pop(queue_key, None)
        keys = _active_queue_keys.get(org_id, [])
        if queue_key in keys:
            keys.remove(queue_key)
    else:
        for key in _active_queue_keys.pop(org_id, []):
            _synthesis_queue.pop(key, None)
