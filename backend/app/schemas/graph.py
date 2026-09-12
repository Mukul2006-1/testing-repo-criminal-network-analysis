"""Phase 4 — graph request schemas (pydantic, via FastAPI)."""

from pydantic import BaseModel, ConfigDict, Field


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(min_length=1, max_length=64,
                           pattern=r"^[A-Za-z0-9_-]{1,64}$")
