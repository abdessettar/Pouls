"""Workouts page: heart rate per minute of each session."""

from apple_health.dashboard import Warehouse, emit, workouts

emit(workouts.heart_rate(Warehouse.locate()))
