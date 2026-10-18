"""Coach page fallback: a snapshot of the coach's journal at build time (the page prefers live data)."""

from apple_health.coach import live
from apple_health.dashboard import emit

emit(live.build())
