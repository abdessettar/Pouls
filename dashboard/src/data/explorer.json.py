"""Every day explorer: column labels, units and formats."""

from apple_health.dashboard import Warehouse, emit, explorer

emit(explorer.build(Warehouse.locate()))
