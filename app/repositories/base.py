"""Base repository abstractions."""

from abc import ABC, abstractmethod
from typing import Any


class BaseUserRepository(ABC):
    """Define the data access contract used by the orchestrator and agents."""

    @abstractmethod
    def get_app_data(self, uid: str) -> dict[str, Any]:
        """Load app-related data for the specified user."""

    @abstractmethod
    def get_behavior_data(self, uid: str) -> dict[str, Any]:
        """Load behavior-related data for the specified user."""

    @abstractmethod
    def get_credit_data(self, uid: str) -> dict[str, Any]:
        """Load credit-related data for the specified user."""

