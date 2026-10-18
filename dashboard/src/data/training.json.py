"""Training page data."""

from apple_health.dashboard import Warehouse, emit, training

emit(training.build(Warehouse.locate()))
