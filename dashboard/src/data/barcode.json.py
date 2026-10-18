"""Night-by-night sleep stages for the barcode charts (Sleep and Overview)."""

from apple_health.dashboard import Warehouse, emit, sleep

emit(sleep.barcode_data(Warehouse.locate()))
