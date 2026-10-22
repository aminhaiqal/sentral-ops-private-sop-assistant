from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DriveFileId = Annotated[str, Field(min_length=5, max_length=180, pattern=r"^[a-zA-Z0-9_-]+$")]


class ConnectionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DriveSource(ConnectionSchema):
    connection_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    file_ids: list[DriveFileId] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def unique_files(self):
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("Select each Drive file only once.")
        return self


class ConnectionView(ConnectionSchema):
    id: str
    provider: Literal["google_drive"] = "google_drive"
    name: str
    status: Literal["connected", "reconnect_required", "disconnected"]
    created_at: str
    checked_at: str


class DriveFile(ConnectionSchema):
    id: DriveFileId
    name: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(max_length=160)
    url: str
    modified_at: str | None = None
    readable: bool


class DriveDocument(ConnectionSchema):
    file: DriveFile
    text: str = Field(max_length=8000)
    truncated: bool


class DriveContextInput(ConnectionSchema):
    source: DriveSource


class DriveContextOutput(ConnectionSchema):
    documents: list[DriveDocument] = Field(max_length=2)
