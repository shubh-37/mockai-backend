from beanie import Document, Link
from pydantic import Field, ConfigDict
from bson import ObjectId
from datetime import date
from typing import Optional
from models.users import User


class Payment(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    transaction_id: str = Field(...)  # New required field for additional payment id
    amount: Optional[float] = None
    payment_date: Optional[date] = None
    user_id: Optional[Link[User]] = None
    reviews_bought: Optional[int] = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "payments"
