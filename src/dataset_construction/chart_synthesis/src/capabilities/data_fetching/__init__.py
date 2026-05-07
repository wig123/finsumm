"""Data Fetching Capability"""
from .fetcher import DataFetcher, DataFetchError
from .adapters import FREDAdapter
from .synthetic_generator import SyntheticDataGenerator, SyntheticDataError

__all__ = [
    "DataFetcher",
    "DataFetchError",
    "FREDAdapter",
    "SyntheticDataGenerator",
    "SyntheticDataError"
]
