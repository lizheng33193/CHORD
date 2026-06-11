"""Request schemas for the analysis API."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator

from app.utils.uid_utils import validate_uid_or_raise


class AnalyzeRequest(BaseModel):
    """Accept either a single uid or a list of uids in one request."""

    uid: Optional[str] = None
    uids: Optional[List[str]] = None
    application_time: Optional[str] = None
    country: Literal["mx", "th"] = "mx"

    @model_validator(mode="before")
    @classmethod
    def validate_uid_input(cls, values: dict) -> dict:
        """Ensure at least one valid uid is provided by the client."""
        uid = (values.get("uid") or "").strip()
        uids = [item.strip() for item in values.get("uids") or [] if item and item.strip()]
        if not uid and not uids:
            raise ValueError("At least one uid must be provided in `uid` or `uids`.")

        if uid:
            values["uid"] = validate_uid_or_raise(uid, field_name="uid")

        if uids:
            values["uids"] = [
                validate_uid_or_raise(item, field_name=f"uids[{index}]")
                for index, item in enumerate(uids)
            ]

        application_time = values.get("application_time")
        if application_time:
            try:
                datetime.fromisoformat(str(application_time).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("`application_time` must be a valid ISO datetime string.") from exc
        return values

    def get_uid_list(self) -> list[str]:
        """Convert the request into a normalized uid list."""
        uid_list: list[str] = []

        if self.uid:
            uid_list.append(self.uid.strip())

        if self.uids:
            uid_list.extend([uid.strip() for uid in self.uids if uid and uid.strip()])

        # Remove duplicates while keeping the original order.
        return [uid for uid in dict.fromkeys(uid_list) if uid]
