"""Placeholder repository for future warehouse integration."""

from __future__ import annotations

from typing import Any

from app.repositories.base import BaseUserRepository


class WarehouseUserRepository(BaseUserRepository):
    """Future implementation for reading from data warehouse."""

    def get_app_data(self, uid: str) -> dict[str, Any]:
        raise NotImplementedError("Warehouse repository is not connected yet.")

    def get_behavior_data(self, uid: str) -> dict[str, Any]:
        raise NotImplementedError("Warehouse repository is not connected yet.")

    def get_credit_data(self, uid: str) -> dict[str, Any]:
        raise NotImplementedError("Warehouse repository is not connected yet.")

