from typing import Optional
from beanie import Document
from pydantic import Field, StringConstraints, ConfigDict
from bson import ObjectId
from typing_extensions import Annotated

IndianMobile = Annotated[str, StringConstraints(pattern=r"^[6-9]\d{9}$")]


class Employee(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    name: Optional[str] = None
    mobile_number: IndianMobile
    email: str
    role_in_company: Optional[str] = None
    password: str
    company_name: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "employee"
