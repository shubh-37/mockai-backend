from pydantic import BaseModel, EmailStr, field_validator, model_validator
from fastapi import UploadFile
import re

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    institute: str
    mobile_number: str
    resume: UploadFile

    @field_validator("mobile_number")
    def validate_mobile_number(cls, value: str) -> str:
        # Example regex for international numbers (starting with +)
        if not re.fullmatch(r"^\+?\d{10,15}$", value):
            raise ValueError("Invalid mobile number. It must be 10-15 digits and may start with '+'.")
        return value
    
class InterviewCreate(BaseModel):
    job_role: str
    industry: str
    overall_experience_yrs: int

    @field_validator("overall_experience_yrs")
    def validate_overall_experience_yrs(cls, value: int) -> int:
        if not value>=0:
            raise ValueError("Invalid Overall Experience (years). It must be greater than zero.")
        return value
    
class InterviewOut(BaseModel):
    message: str
    interview_id: int
    
class InterviewFeedback(BaseModel):
    overall_score: int
    speech: int
    confidence: int
    technical_skills: int
    areas_of_improvement: str
    
class UserLogin(BaseModel):
    email: str
    password: str

class Message(BaseModel):
    message: str

class UserResponse(BaseModel):
    response: str

class UserOut(BaseModel):
    email: str
    message: str

class Feedback(BaseModel):
    overall_experience: int
    recommend_score: int
    pay_for_report: bool = False
    pay_price: int = None
    suggestions: str

    @field_validator("overall_experience")
    def validate_overall_experience(cls, value: int) -> int:
        if not (value >=1 or value <=5):
            raise ValueError("Invalid Value. Overall Experience should be rated between 1 to 5.")
        return value
    
    @field_validator("recommend_score")
    def validate_recommend_score(cls, value: int) -> int:
        if not (value >=1 or value <=5):
            raise ValueError("Invalid Value. Recommend Score should be rated between 1 to 5.")
        return value
    
    @model_validator(mode="after")
    def validate_pay(cls, values):
        price = values.pay_price
        pay = values.pay_for_report
        if pay and (price is None or price < 0):
            raise ValueError("Price must be provided and >= 0 if the pay for report is set to True.")
        return values

