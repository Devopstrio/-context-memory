from datetime import datetime, timedelta, timezone

from context_memory.models.memory import Memory


class RetentionPolicy:
    """Applies data retention policies to memories."""

    def __init__(self, default_ttl_days: int = 90) -> None:
        self.default_ttl = default_ttl_days

    def apply_policy(self, memory: Memory) -> Memory:
        """Set an expiration date if none is already set."""
        if memory.expires_at is None:
            memory.expires_at = datetime.now(timezone.utc) + timedelta(days=self.default_ttl)
        return memory

    def is_expired(self, memory: Memory) -> bool:
        """Check if a memory has expired."""
        if memory.expires_at is None:
            return False
        return datetime.now(timezone.utc) > memory.expires_at
