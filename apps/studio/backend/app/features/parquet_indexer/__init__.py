"""Parquet Indexer feature.

This feature polls the filesystem for Parquet files written by the ingestion service,
extracts span metadata, and indexes it into the SQLite metadata database for fast lookups.
"""
