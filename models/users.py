from typing import Optional
from beanie import Document, Link
from models.company import Company
from pydantic import Field, StringConstraints, ConfigDict
from bson import ObjectId
from typing_extensions import Annotated

IndianMobile = Annotated[str, StringConstraints(pattern=r"^[6-9]\d{9}$")]


class User(Document):
    id: ObjectId = Field(default_factory=lambda: ObjectId())
    name: str
    email: str
    mobile_number: IndianMobile
    country_code: Optional[str] = None
    resume: Optional[str] = None
    job_role: Optional[str] = None
    years_of_experience: Optional[int] = None
    field: Optional[str] = None
    organization: Optional[Link[Company]] = None
    aboutMe: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "users"

    def resume_url(self) -> Optional[str]:
        if not self.resume:
            return None
        bucket_name = "prepsom-resume"
        return f"https://storage.googleapis.com/{bucket_name}/{self.resume}"
