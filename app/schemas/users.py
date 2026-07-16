from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class UserProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_url: HttpUrl | None = Field(default=None, max_length=2048)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Nome inválido.")
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value
