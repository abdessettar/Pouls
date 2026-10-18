"""Steps and heart rate per local hour for every valid wear day (Activity and Heart)."""

from apple_health.dashboard import Warehouse, emit, hourly

emit(hourly.build(Warehouse.locate()))
