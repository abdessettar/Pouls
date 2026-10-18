"""Running page data."""

from apple_health.dashboard import Warehouse, emit, running

emit(running.build(Warehouse.locate()))
