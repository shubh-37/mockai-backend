import uuid
from typing import List, Optional, Literal
from pydantic import Field, ConfigDict
from beanie import Document, Link
from bson import ObjectId
from datetime import datetime

# ----- User, Company, Payment (existing models) -----
from models.users import User
from models.company import Company
from models.payment import Payment
from models.user_aptitude import UserAptitude


# Free Review Models
class CommunicationSkills(Document):
    clarity: Optional[float] = None  # e.g. 0–100
    articulation: Optional[float] = None  # e.g. 0–100
    active_listening: Optional[float] = None  # e.g. 0–100


class ConceptualUnderstanding(Document):
    fundamental_concepts: Optional[float] = None
    theoretical_application: Optional[float] = None
    analytical_reasoning: Optional[float] = None


class SpeechAnalysisMetrics(Document):
    avg_filler_words_used: Optional[float] = None
    avg_confidence_level: Optional[str] = None  # e.g. "High", "Medium"
    avg_fluency_rate: Optional[float] = None  # e.g. 0–100


class TimeManagement(Document):
    average_response_time: Optional[str] = None  # e.g. "1 min 20s"
    question_completion_rate: Optional[float] = None
    total_time_spent: Optional[str] = None  # e.g. 95.0


class SkillAnalysis(Document):
    communication_skills: Optional[CommunicationSkills] = None
    conceptual_understanding: Optional[ConceptualUnderstanding] = None
    speech_analysis: Optional[SpeechAnalysisMetrics] = None
    time_management: Optional[TimeManagement] = None


class StrengthWeaknessItem(Document):
    type: Literal["strength", "weakness"]
    title: str
    description: str


# Paid Review Models


class QuestionAnalysis(Document):
    question: str
    question_id: str
    quick_analysis: Optional[str] = None
    apt_answer: Optional[str] = None


class PerformanceMetrics(Document):

    # ---------- 1. Cognitive Analysis (Radar Chart) ----------
    critical_thinking: Optional[float] = None  # e.g. 0-100
    logical_reasoning: Optional[float] = None
    problem_solving: Optional[float] = None
    adaptability: Optional[float] = None
    creativity: Optional[float] = None

    # ---------- 2. Domain/Subject Proficiency (Pie Chart) ----------
    foundational_knowledge: Optional[float] = None
    advanced_concepts: Optional[float] = None
    practical_application: Optional[float] = None

    # ---------- 3. Communication Skills (Bar Chart) ----------
    articulation: Optional[float] = None
    technical_terms: Optional[float] = None
    active_listening: Optional[float] = None


class CareerPathRecommendations(Document):
    recommended_role: Optional[str] = None
    skill_match: Optional[float] = None
    skills: Optional[List[str]] = None


class FreeReview(Document):
    overall_score: Optional[float] = None
    overall_summary: Optional[str] = None
    skill_analysis: Optional[SkillAnalysis] = None
    strengths_and_weaknesses: Optional[List[StrengthWeaknessItem]] = Field(default=None)


class PaidReview(Document):

    question_analysis: Optional[List[QuestionAnalysis]] = None
    performance_metrics: Optional[PerformanceMetrics] = None
    career_path_recommendations: Optional[List[CareerPathRecommendations]] = None
    # learning resources can also be added here


class SpeechAnalysis(Document):

    transcript: Optional[str] = None
    fluency_score: Optional[float] = None
    confidence_score: Optional[float] = None
    filler_words: Optional[List[str]] = None
    time_seconds: Optional[float] = None
    clarity_score: Optional[float] = None
    words_per_minute: Optional[float] = None
    answer_relevance_score: Optional[float] = None


class QuestionResponse(Document):
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    speech_analysis: Optional[SpeechAnalysis] = None


class CustomerFeedback(Document):
    rating: int
    suggestion: str
    user_id: Link[User]


class Interview(Document):
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[Link[User]] = None
    company_id: Optional[Link[Company]] = None
    payment_id: Optional[Link[Payment]] = None
    user_aptitude_id: Optional[Link[UserAptitude]] = None

    question_responses: Optional[List[QuestionResponse]] = None
    customer_feedback: Optional[CustomerFeedback] = None

    free_review: Optional[FreeReview] = None
    paid_review: Optional[PaidReview] = None
    user_data: Optional[dict] = (
        Field(
            default=None,
        ),
    )
    completion_percentage: Optional[float] = 0
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "interview"
