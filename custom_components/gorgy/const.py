"""Constants for the Gorgy Timing integration."""

from datetime import timedelta

DOMAIN = "gorgy"
MANUFACTURER = "Gorgy Timing"

# The clock does not push changes, so it is polled.
SCAN_INTERVAL = timedelta(seconds=30)

# /menu feature flag of models with a stopwatch
FEATURE_STOPWATCH = "chrono"

STORAGE_VERSION = 1
