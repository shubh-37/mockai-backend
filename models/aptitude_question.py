from beanie import Document
from pydantic import Field, ConfigDict
from bson import ObjectId
from typing import List


class AptitudeQuestion(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    question: str
    options: List[str]
    answer: str
    level: str
    topic: str

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "aptitude_question"
