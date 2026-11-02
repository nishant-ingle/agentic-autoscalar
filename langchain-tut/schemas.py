from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field


@dataclass
class Context:
    user_id: str


class ResponseFormat(BaseModel):
    clarification_question: Optional[str] = Field(
        default=None,
        description="Ask the user for missing details (e.g. city) if location is unknown"
    )
    summary: Optional[str] = Field(
        default=None,
        description="Brief textual summary of the current weather condition"
    )
    temperature_celsius: Optional[float] = Field(default=None)
    temperature_fahrenheit: Optional[float] = Field(default=None)
    humidity: Optional[float] = Field(default=None)
