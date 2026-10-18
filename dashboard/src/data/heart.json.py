"""Heart page data."""

from apple_health.dashboard import Warehouse, emit, heart

emit(heart.build(Warehouse.locate()))
