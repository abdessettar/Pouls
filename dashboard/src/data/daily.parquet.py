"""Every day explorer rows: mart_daily as Parquet."""

from apple_health.dashboard import Warehouse, emit_parquet, explorer

emit_parquet(explorer.frame(Warehouse.locate()))
