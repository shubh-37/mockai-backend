from pydantic import BaseModel, EmailStr, field_validator, model_validator
from fastapi import UploadFile
import re
from typing import Optional, List, Union

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    
class UserProfile(BaseModel):
    institute: Optional[str] = None
    mobile_number: Optional[str] = None
    resume: Union[UploadFile, bool] = None 
    yrs_of_exp: Optional[int] = None
    job_role: Optional[str] = None
    company: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    
    @field_validator("yrs_of_exp")
    def validate_yrs_of_exp(cls, value: int) -> int:
        if not value>=0:
            raise ValueError("Invalid Experience (years). It must be greater than zero.")
        return value
    
    @field_validator("mobile_number")
    def validate_mobile_number(cls, value: str) -> str:
        # Example regex for international numbers (starting with +)
        if not re.fullmatch(r"^\+?\d{10,15}$", value):
            raise ValueError("Invalid mobile number. It must be 10-15 digits and may start with '+'.")
        return value
    
class InterviewOut(BaseModel):
    questions: List[str]
    interview_id: int
    company_logo: str
    
class InterviewFeedback(BaseModel):
    overall_score: int
    speech: int
    confidence: int
    technical_skills: int
    areas_of_improvement: List[str]
    
class UserLogin(BaseModel):
    email: str
    password: str

class Message(BaseModel):
    message: str

class QAA(BaseModel):
    question: str
    answer: str

class InterviewResponse(BaseModel):
    interview_id:int
    qaa: List[QAA]

class UserOut(BaseModel):
    username: str
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

