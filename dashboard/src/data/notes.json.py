"""Notes page data: references and sources, coverage, devices, what is not shown."""

from apple_health.dashboard import Warehouse, emit, notes

emit(notes.build(Warehouse.locate()))
