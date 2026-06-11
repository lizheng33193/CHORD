"""Shared Data Acquisition capability checks."""

from __future__ import annotations

import os
from dataclasses import dataclass


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class DataAcquisitionCapability:
    mode: str
    enabled: bool
    reason: str | None = None


def get_data_acquisition_mode() -> str:
    raw = os.getenv("DATA_ACQUISITION_ENABLED")
    if raw is None or not str(raw).strip():
        return "auto"
    value = str(raw).strip().lower()
    if value in _TRUE_VALUES:
        return "required"
    if value in _FALSE_VALUES:
        return "disabled"
    raise RuntimeError(
        "Invalid DATA_ACQUISITION_ENABLED value. "
        "Use true/false or leave unset for auto."
    )


def get_data_acquisition_capability() -> DataAcquisitionCapability:
    mode = get_data_acquisition_mode()
    if mode == "disabled":
        return DataAcquisitionCapability(mode=mode, enabled=False, reason="disabled_by_config")

    try:
        __import__("data_acquisition_agent.executor", fromlist=["run_execute_pipeline"])
        __import__("data_acquisition_agent.api", fromlist=["router"])
    except ModuleNotFoundError as exc:
        if mode == "required":
            raise RuntimeError(
                "DATA_ACQUISITION_ENABLED=true but Data Acquisition dependencies "
                f"could not be imported: {exc}"
            ) from exc
        return DataAcquisitionCapability(
            mode=mode,
            enabled=False,
            reason=f"missing_dependency:{getattr(exc, 'name', str(exc))}",
        )
    except Exception as exc:  # noqa: BLE001
        if mode == "required":
            raise RuntimeError(
                "DATA_ACQUISITION_ENABLED=true but Data Acquisition imports failed: "
                f"{exc}"
            ) from exc
        return DataAcquisitionCapability(
            mode=mode,
            enabled=False,
            reason=f"import_error:{exc.__class__.__name__}",
        )

    return DataAcquisitionCapability(mode=mode, enabled=True, reason=None)


def data_acquisition_unavailable_message(capability: DataAcquisitionCapability) -> str:
    if capability.reason == "disabled_by_config":
        return "当前环境未启用数据获取能力，请直接提供 UID 或上传 UID 文件。"
    return "当前环境缺少可用的数据获取执行依赖，请直接提供 UID 或上传 UID 文件。"
