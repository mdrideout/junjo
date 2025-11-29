"""Parquet Indexer feature for V4 architecture.

This feature polls the filesystem for Parquet files written by Go ingestion,
extracts span metadata, and indexes it into DuckDB for fast listing queries.
"""
