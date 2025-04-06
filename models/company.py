from beanie import Document, Link
from pydantic import Field, ConfigDict
from bson import ObjectId
from typing import Any, Dict, Optional, List
from models.employee import Employee


class Company(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    name: str
    logo: str
    interview_settings: Dict[str, Any]
    employees: Optional[List[Link[Employee]]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "company"
