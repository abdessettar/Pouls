"""Places page data."""

from apple_health.dashboard import Warehouse, emit, places

emit(places.build(Warehouse.locate()))
