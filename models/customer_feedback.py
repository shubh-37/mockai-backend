from beanie import Document, Link
from models.interview import Interview
from pydantic import Field, ConfigDict
from bson import ObjectId
from models.users import User


class CustomerFeedback(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    rating: int = None
    suggestion: str = None
    user_id: Link[User]
    interview_id: Link[Interview]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "customer_feedback"
