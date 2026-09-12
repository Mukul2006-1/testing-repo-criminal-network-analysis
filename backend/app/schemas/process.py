"""Phase 2 — API request schemas (pydantic, via FastAPI).

Only shapes the service layer does not already validate; services remain
stdlib-only so they stay testable without web dependencies.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProcessOptions = dict  # validated loosely; unknown flags are ignored


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(min_length=1, max_length=64,
                           pattern=r"^[A-Za-z0-9_-]{1,64}$")
    options: dict = Field(default_factory=dict)


class JobResponse(BaseModel):
    job_id: str
    upload_id: str
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL"]
