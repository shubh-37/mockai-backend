from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re
from typing import Optional, List, Union


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    mobile_number: str
    country_code: Optional[str] = None


class UserProfile(BaseModel):
    organization: Optional[str] = None
    mobile_number: Optional[str] = None
    years_of_experience: Optional[int] = None
    job_role: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    field: Optional[str] = None

    @field_validator("years_of_experience")
    def validate_yrs_of_exp(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError(
                "Invalid Experience (years). It cannot be negative."
            )
        return value

    @field_validator("mobile_number")
    def validate_mobile_number(cls, value: str) -> str:
        # Example regex for international numbers (starting with +)
        if not re.fullmatch(r"^\+?\d{10,15}$", value):
            raise ValueError(
                "Invalid mobile number. It must be 10-15 digits and may start with '+'."
            )
        return value


class InterviewCreateOut(BaseModel):
    interview_id: str
    company_logo: str


class InterviewQuestionsOut(BaseModel):
    questions: List
    interview_id: str


class Message(BaseModel):
    message: str


class Feedback(BaseModel):
    overall_experience: int
    recommend_score: int
    pay_for_report: bool = False
    pay_price: int = None
    suggestions: str

    @field_validator("overall_experience")
    def validate_overall_experience(cls, value: int) -> int:
        if not (value >= 1 or value <= 5):
            raise ValueError(
                "Invalid Value. Overall Experience should be rated between 1 to 5."
            )
        return value

    @field_validator("recommend_score")
    def validate_recommend_score(cls, value: int) -> int:
        if not (value >= 1 or value <= 5):
            raise ValueError(
                "Invalid Value. Recommend Score should be rated between 1 to 5."
            )
        return value

    @model_validator(mode="after")
    def validate_pay(cls, values):
        price = values.pay_price
        pay = values.pay_for_report
        if pay and (price is None or price < 0):
            raise ValueError(
                "Price must be provided and >= 0 if the pay for report is set to True."
            )
        return values


class TextToSpeechRequest(BaseModel):
    text: str


class QuizSubmissionRequest(BaseModel):
    answers: object
    topics: List[str]


class VerifySignupOTPRequest(BaseModel):
    email: str
    email_otp: int


class VerifyOtpResponse(BaseModel):
    token: str
    user: str


class AboutRequest(BaseModel):
    about: str


class SendOtpRequest(BaseModel):
    email: str


class VerifyOtpRequest(BaseModel):
    email: str
    otp: int


class OtpResponse(BaseModel):
    message: str
    flag: bool


class VerifyPaymentInput(BaseModel):
    order_id: str
    payment_id: str
    signature: str
    reviews_bought: int = 1


class Employee(BaseModel):
    email: str
    mobile_number: str
    name: str
    role_in_company: str
    company_name: str
    password: str


class LoginEmployee(BaseModel):
    email: str
    password: str
