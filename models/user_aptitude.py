from beanie import Document, Link
from pydantic import Field, ConfigDict
from bson import ObjectId
from models.users import User
from typing import Optional
from datetime import datetime


class UserAptitude(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    created_at: datetime = Field(default_factory=datetime.utcnow)
    correct_no_of_questions: int
    wrong_no_of_answers: int
    score: float
    user_id: Link[User]
    topics: Optional[list[str]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "user_aptitudes"
