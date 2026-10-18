"""Sleep page data."""

from apple_health.dashboard import Warehouse, emit, sleep

emit(sleep.build(Warehouse.locate()))
