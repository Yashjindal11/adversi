from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    """Base for all persisted protocol records.

    ``extra="ignore"`` lets older readers load results written by newer versions;
    additive fields are therefore non-breaking. Removing or renaming fields requires
    bumping ``RESULT_SCHEMA_VERSION``.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
