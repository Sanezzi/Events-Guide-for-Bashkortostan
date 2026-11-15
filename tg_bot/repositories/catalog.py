"""Compatibility import for older integrations."""

from .catalog_repo import CatalogRepositoryProtocol, SqlCatalogRepository

__all__ = ["CatalogRepositoryProtocol", "SqlCatalogRepository"]
