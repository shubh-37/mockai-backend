import os
import logging
from fastapi import FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import json

load_dotenv()

# Initialize FastAPI
app = FastAPI()

# Configure Logging
logging.basicConfig(level=logging.INFO)

# Initialize Free OpenAI model (for general use)
best_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"), model_name="gpt-4o", temperature=0.7
)

fast_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="gpt-3.5-turbo-1106",
    temperature=0.7,
)

free_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="gpt-3.5-turbo",
    temperature=0.2,
)


class InterviewInput(BaseModel):
    job_role: str
    company: str


class InterviewResponse(BaseModel):
    responses: list  # List of answers


class FeedbackInput(BaseModel):
    qaa: str


# def create_dynamic_question_agent():
#     template = """
#         Greet the candidate warmly in real time. Start by asking a friendly, conversational introductory question that prompts the candidate to introduce themselves.

#         Then, generate 9 additional unique and well-structured interview questions for a candidate applying for the role of {job_role} at {company} in the field of {field}, with {years_of_experience} years of experience.

#         The questions should be balanced as follows:
#         - At least three deeply technical questions that test core expertise based on the candidate's resume ({resume}).
#         - The remaining six should assess problem-solving, frameworks/tools proficiency, real-world application, best practices, debugging, and cultural fit.

#         Structure:
#         1. Ask the candidate to introduce themselves in a natural, friendly way.
#         2. Ask a specific, deeply technical question based on the resume to assess core expertise.
#         3. Ask a technical question focused on a different relevant skill or area of expertise.
#         4. Pose an advanced or specialized technical scenario to assess depth of knowledge.
#         5. Present a realistic problem-solving scenario they might face in this role.
#         6. Ask a question that assesses understanding of industry best practices or optimization strategies.
#         7. Evaluate proficiency with key frameworks/tools mentioned in the resume.
#         8. Present a debugging or edge-case troubleshooting scenario relevant to the job field.
#         9. Ask a question that explores knowledge of current trends or innovations in the field.
#         10. Ask a question that evaluates cultural fit, communication, or teamwork skills in the workplace.

#         Return a JSON object in the following format (with no placeholder text):
#         {{
#         "greeting": "Your warm greeting message",
#         "questions": [
#             "Conversational introductory question...",
#             "Fully-formed technical question 1...",
#             "Fully-formed technical question 2...",
#             "Advanced technical scenario question...",
#             "Real-world problem-solving scenario...",
#             "Best practices and optimization question...",
#             "Frameworks/tools proficiency question...",
#             "Debugging or edge case handling scenario...",
#             "Trends/innovation awareness question...",
#             "Cultural fit or teamwork question..."
#         ]
#         }}
#         """
#     prompt = PromptTemplate(
#         template=template,
#         input_variables=[
#             "job_role",
#             "company",
#             "resume",
#             "years_of_experience",
#             "field",
#         ],
#     )
#     return LLMChain(llm=llm, prompt=prompt)


def create_dynamic_question_agent():
    template = """
You are a smart and friendly interview assistant.

Your goal is to generate exactly 10 thoughtful and well-structured interview questions, beginning with a warm, friendly introduction.

---

**Candidate Info**
- Role: {job_role}
- Company: {company}
- Field: {field}
- Years of Experience: {years_of_experience}

**Resume Summary:**
{resume_summary}

{previous_questions_section}

---

**Instructions**

1. **Introductory Question (Q1)**:
   - Start with a friendly, warm, and conversational prompt asking the candidate to introduce themselves.
   - This question must always be included.

2. **Questions 2–10** must be:
   - Professionally written
   - Role-specific
   - Personalized based on the resume summary (tools, domains, responsibilities, strengths)
   - Diverse — covering multiple facets such as domain knowledge, tools, thinking style, communication, etc.

3. If "{company}" is a well-known firm (e.g., Meta, McKinsey, Deloitte, Amazon), include 1–2 questions inspired by its typical interview approach (e.g., structured thinking, leadership scenarios, estimation).

4. You must generate exactly 10 questions including the intro. Do not stop at 9.

5. Do not repeat or closely mirror any of the candidate’s previously asked questions (if provided).

---

Output only a valid JSON object in the following format. Do not include anything else:
{{
  "greeting": "<warm greeting message>",
  "questions": [
    "<Intro question - Q1>",
    "<Q2>",
    "<Q3>",
    "...",
    "<Q10>"
  ]
}}
"""

    prompt = PromptTemplate(
        template=template,
        input_variables=[
            "job_role",
            "company",
            "resume_summary",
            "years_of_experience",
            "field",
            "previous_questions_section",
        ],
    )

    return LLMChain(llm=fast_llm, prompt=prompt)


def generate_initial_question(
    job_role: str,
    company: str,
    resume_summary: str,
    years_of_experience: int,
    field: str,
    previous_questions: list[str] = None,
):
    agent = create_dynamic_question_agent()

    previous_questions_section = (
        "Previously asked questions (do not repeat or paraphrase):\n"
        + "\n".join([f"- {q}" for q in previous_questions])
        if previous_questions
        else "No previous questions. This is the candidate's first interview."
    )

    return agent.invoke(
        {
            "job_role": job_role,
            "company": company,
            "resume_summary": resume_summary,
            "years_of_experience": years_of_experience,
            "field": field,
            "previous_questions_section": previous_questions_section,
        }
    )


# def create_feedback_analysis_agent():
#     template = """
# You are a highly experienced and consistent interview evaluator. Based on the candidate's interview responses provided below as JSON, generate a detailed and structured JSON report that strictly follows the FreeReview schema.

# Key Instructions:
# 1. Each answered question must be individually scored from 0 to 10 based on quality, clarity, and relevance. Unanswered questions = 0.
# 2. The overall score = sum of individual question scores. Maximum possible score is {max_score}.
# 3. The overall summary must reflect specific analysis and give the candidate 2-3 clear and constructive feedback points.
# 4. Skill analysis must be *relative and proportional* to the completeness, consistency, and quality of *all responses together*, not just one.
# 5. Use the following criteria for skill metrics:
#    - *Clarity* and *articulation* scale with how clearly and consistently all answers are written and explained.
#    - *Active listening* should be tied to how well the candidate addresses the core of each question across the board, not just one.
#    - *Conceptual skills* should reflect understanding demonstrated in multiple answers. If only one answer is strong, scale scores accordingly.
#    - *Speech scores* must be averaged estimates across all responses, and penalize vague, short, or incomplete answers.
# 6. Cap the maximum skill sub-score (out of 100) to be no higher than the average percentage of answered questions and quality across responses.
# 7. Avoid random zeros or overinflated 90+ values unless responses consistently justify them.
# 8. Include exactly 3 strengths and 3 weaknesses based on real patterns in the responses.
# 9. Include completion rate as: (answered_questions / total_questions) * 100, rounded to nearest integer.

# Candidate Responses:
# {responses}

# Output the JSON object in exactly this format:
# {{
#   "overall_score": <realistic total score from 0 to {max_score}>,
#   "overall_summary": "<2-3 sentence feedback directly to candidate>",

#   "skill_analysis": {{
#      "communication_skills": {{
#          "clarity": <0-100>,
#          "articulation": <0-100>,
#          "active_listening": <0-100>
#      }},
#      "conceptual_understanding": {{
#          "fundamental_concepts": <0-100>,
#          "theoretical_application": <0-100>,
#          "analytical_reasoning": <0-100>
#      }},
#      "speech_analysis": {{
#          "avg_filler_words_used": <integer>,
#          "avg_confidence_level": "<High|Medium|Low>",
#          "avg_fluency_rate": <0-100>
#      }},
#      "time_management": {{
#          "average_response_time": "<e.g., '35 seconds'>",
#          "question_completion_rate": <int: percentage of answered questions>,
#          "total_time_spent": "<e.g., '3 minutes 4 seconds'>"
#      }}
#   }},
#   "strengths_and_weaknesses": [
#      {{
#         "type": "strength",
#         "title": "<strength title>",
#         "description": "<detailed explanation>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<another strength title>",
#         "description": "<detailed explanation>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<another strength title>",
#         "description": "<detailed explanation>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<weakness title>",
#         "description": "<detailed explanation>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<another weakness title>",
#         "description": "<detailed explanation>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<another weakness title>",
#         "description": "<detailed explanation>"
#      }}
#   ]
# }}
# """

#     prompt = PromptTemplate(
#         template=template,
#         input_variables=[
#             "responses",
#             "total_questions",
#             "answered_questions",
#             "max_score",
#         ],
#     )
#     return LLMChain(llm=llm, prompt=prompt)


def create_feedback_analysis_agent():
    template = """
You are a highly consistent and objective interview evaluator.

You are reviewing structured interview responses. Each response contains:
- `question`: the question asked
- `speech_analysis`: an object with the candidate's transcripted answer and speaking metrics

Inside `speech_analysis`, you'll find:
- transcript: the full answer text
- fluency_score, confidence_score, clarity_score
- filler_words, words_per_minute, time_seconds
- answer_relevance_score and observation

You must generate a complete evaluation based on:
- How well the candidate answered each question (content + relevance)
- How clearly and confidently they spoke
- Trends or patterns in delivery, speech, or gaps across answers

### Scoring Instructions:
1. Score each answered question from 0 to 10 (unanswered = 0)
2. overall_score = sum of scores across all questions (max: {max_score})
3. Use `speech_analysis.transcript` for qualitative judgments
4. Use fluency, confidence, clarity, and relevance scores as secondary signals
5. Use completion percentage to scale skill scores proportionally
6. Be realistic — avoid inflated 90+ values unless consistently earned

### Final Output Must Include:

- A 2–3 sentence `overall_summary`
- `skill_analysis` with 4 sub-categories:
  - communication_skills
  - conceptual_understanding
  - speech_analysis
  - time_management
- Exactly 3 strengths and 3 weaknesses based on real recurring traits

Completion Rate = (answered_questions / total_questions) * 100

Candidate Responses:
{responses}

Now return only a valid JSON object in this structure:
{{
  "overall_score": <0–{max_score}>,
  "overall_summary": "<summary>",
  "skill_analysis": {{
    "communication_skills": {{
      "clarity": <0–100>,
      "articulation": <0–100>,
      "active_listening": <0–100>
    }},
    "conceptual_understanding": {{
      "fundamental_concepts": <0–100>,
      "theoretical_application": <0–100>,
      "analytical_reasoning": <0–100>
    }},
    "speech_analysis": {{
      "avg_filler_words_used": <int>,
      "avg_confidence_level": "<High|Medium|Low>",
      "avg_fluency_rate": <0–100>
    }},
    "time_management": {{
      "average_response_time": "<e.g., '35 seconds'>",
      "question_completion_rate": <int>,
      "total_time_spent": "<e.g., '3 minutes 4 seconds'>"
    }}
  }},
  "strengths_and_weaknesses": [
    {{
      "type": "strength",
      "title": "<...>",
      "description": "<...>"
    }},
    ...
    {{
      "type": "weakness",
      "title": "<...>",
      "description": "<...>"
    }}
  ]
}}
"""
    prompt = PromptTemplate(
        template=template,
        input_variables=[
            "responses",
            "total_questions",
            "answered_questions",
            "max_score",
        ],
    )
    return LLMChain(llm=fast_llm, prompt=prompt)


def create_feedback_analysis_agent_paid():
    template = """
You are a seasoned interview evaluator and career coach.

Your task is to:
1. Review each of the candidate's responses (answered or not) and provide consistent evaluation.
2. Score key performance areas (0–100 scale).
3. Suggest 3 career paths based on the overall skill profile.
4. Generate an ideal answer ("apt_answer") for every question.

Each item in the list below represents a question object. All of them MUST be evaluated in your response.

Each object contains:
- `question`: the actual question
- `question_id`: a unique reference
- `answer`: the candidate's answer text or `null` (if unanswered)

There are {question_count} questions total. You must return exactly {question_count} items in the `question_analysis` array — even if some answers are empty or vague.

If a question is not answered (null or empty), still include a realistic analysis and an ideal model answer.

Candidate's experience: {years_of_experience} years

Candidate Responses:
{responses}

Strictly return only a raw JSON object with the following structure without wrapping it in markdown, code blocks, or extra text:

{{
  "question_analysis": [
    {{
      "question": "<original question>",
      "question_id": "<unique id>",
      "quick_analysis": "<evaluation of the given answer — or 'Not answered, but expected...' if missing>",
      "apt_answer": "<ideal answer to this question>"
    }}
  ],
  "performance_metrics": {{
    "critical_thinking": <0-100>,
    "logical_reasoning": <0-100>,
    "problem_solving": <0-100>,
    "adaptability": <0-100>,
    "creativity": <0-100>,
    "foundational_knowledge": <0-100>,
    "advanced_concepts": <0-100>,
    "practical_application": <0-100>,
    "articulation": <0-100>,
    "technical_terms": <0-100>,
    "active_listening": <0-100>
  }},
  "career_path_recommendations": [
    {{
      "recommended_role": "<title>",
      "skill_match": <0-100>,
      "skills": ["<skill1>", "<skill2>", "<skill3>"]
    }},
    {{
      "recommended_role": "<title>",
      "skill_match": <0-100>,
      "skills": ["<skill1>", "<skill2>", "<skill3>"]
    }},
    {{
      "recommended_role": "<title>",
      "skill_match": <0-100>,
      "skills": ["<skill1>", "<skill2>", "<skill3>"]
    }}
  ]
}}
"""
    prompt = PromptTemplate(
        template=template,
        input_variables=["responses", "years_of_experience", "question_count"],
    )
    return LLMChain(llm=best_llm, prompt=prompt)


def generate_feedback(qaa: str, total: int, answered: int, max_score: int):
    agent = create_feedback_analysis_agent()
    return agent.invoke(
        {
            "responses": qaa,
            "total_questions": total,
            "answered_questions": answered,
            "max_score": max_score,
        }
    )


def generate_feedback_paid(qaa: str, years_of_experience: int):
    try:
        parsed = json.loads(qaa)
        question_count = len(parsed)
    except Exception as e:
        logging.error("Failed to parse QAA: %s", e)
        question_count = 0

    agent = create_feedback_analysis_agent_paid()
    return agent.invoke(
        {
            "responses": qaa,
            "years_of_experience": years_of_experience,
            "question_count": question_count,
        }
    )


def create_resume_summary_agent():
    template = """
    Carefully read and analyze the following resume content.

    Your task is to write a single, well-structured paragraph summarizing the candidate’s:
    - Core technical skills
    - Tools and frameworks used
    - Industry/domain experience
    - Notable achievements or strengths

    Summary Requirements:
    - Output only one cohesive paragraph
    - Do not use bullet points, lists, or headings
    - Keep the tone professional, concise, and neutral
    - Do not include any introductory or closing statements
    - Limit the output to approximately 80 to 120 words

    Resume:
    {resume_text}

    Return only the final summary paragraph.
    """

    prompt = PromptTemplate(template=template, input_variables=["resume_text"])
    return LLMChain(llm=free_llm, prompt=prompt)


def summarize_resume(resume_text: str) -> str:
    try:
        wrapper = create_resume_summary_agent()
        response = wrapper.invoke({"resume_text": resume_text})
        return response.get("text", "").strip()
    except Exception as e:
        logging.error(f"LangChain resume summarization failed: {e}")
        return ""


def create_audio_analysis_agent_with_question():
    template = """
    You are a communication coach evaluating an interview candidate's spoken response.

    Below is the interview question and the candidate's transcripted response, with the total speaking duration in seconds.

    Question:
    {question_text}

    Transcript:
    {transcript_text}

    Duration: {duration_seconds} seconds

    Evaluate the following based on:
    - How well the candidate understood and addressed the question
    - Their communication skills: fluency, confidence, and clarity
    - Their delivery style: pacing, filler usage, and coherence

    Output a JSON object in this format with no extra text:
    {{
      "fluency_score": <float>,               // 0 to 100
      "confidence_score": <float>,            // 0 to 100
      "clarity_score": <float>,               // 0 to 100
      "words_per_minute": <float>,
      "filler_words_used": ["list", "of", "fillers"],
      "answer_relevance_score": <float>,      // 0 to 100 - how well they answered the question
    }}
    """

    prompt = PromptTemplate(
        template=template,
        input_variables=["question_text", "transcript_text", "duration_seconds"],
    )

    return LLMChain(llm=fast_llm, prompt=prompt)


def analyze_audio(
    question_text: str, transcript_text: str, duration_seconds: int
) -> dict:
    try:
        wrapper = create_audio_analysis_agent_with_question()
        return wrapper.invoke(
            {
                "question_text": question_text,
                "transcript_text": transcript_text,
                "duration_seconds": duration_seconds,
            }
        )

    except Exception as e:
        logging.error(f"LangChain resume summarization failed: {e}")
        return ""


# Log success
logging.info("AI wrapper is up and running successfully.")
