"""Phase 3 — extract/resolve request schemas (pydantic, via FastAPI).

Temp extraction IDs are echoed for traceability only; canonical IDs are
always assigned server-side by the resolver and never accepted from input.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal["PERSON", "PHONE", "LOCATION", "VEHICLE",
                     "ORGANIZATION", "DATE", "ACCOUNT"]


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str | None = Field(default=None, max_length=64,
                                  pattern=r"^[A-Za-z0-9_-]{1,64}$")
    text: str | None = Field(default=None, max_length=200_000)
    document_id: str | None = Field(default=None, max_length=64)
    known_names: list[str] = Field(default_factory=list, max_length=5000)
    known_locations: list[str] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if bool(self.upload_id) == bool(self.text):
            raise ValueError("Provide exactly one of upload_id or text.")
        if self.text is not None and not self.document_id:
            raise ValueError("document_id is required with text.")
        return self


class ExtractedEntity(BaseModel):
    # Unknown fields are ignored (not trusted): extraction output carries
    # provenance extras (raw_text, nlp_backend) that resolve does not need.
    # Only the contract fields below are consumed.
    model_config = ConfigDict(extra="ignore")

    id: str = Field(max_length=64)
    type: EntityType
    value: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)
    normalized_value: str | None = Field(default=None, max_length=256)
    method: str | None = Field(default=None, max_length=64)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=64)
    entities: list[ExtractedEntity] = Field(max_length=500)
    doc_attrs: dict = Field(default_factory=dict)
    fuzzy_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
