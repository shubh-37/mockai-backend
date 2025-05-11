import os
import logging
from fastapi import FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

load_dotenv()

# Initialize FastAPI
app = FastAPI()

# Configure Logging
logging.basicConfig(level=logging.INFO)

# Initialize Free OpenAI model (for general use)
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="gpt-4",
    temperature=0.7,
    max_tokens=1024,
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

        Step 1: Greet the candidate warmly. Start with a friendly, conversational introductory question that invites them to introduce themselves.

        Step 2: Generate 9 thoughtful and well-balanced interview questions tailored to a candidate applying for the role of {job_role} at {company}, in the field of {field}, with {years_of_experience} years of experience.

        Step 3: Use the following resume summary to guide your questions. Focus on:
        - Core skills and competencies
        - Tools, systems, or methodologies mentioned
        - Past industries, job functions, or responsibilities
        - Any notable achievements or standout traits

        Resume Summary:
        {resume_summary}

        Step 4: If the company "{company}" is well-known (e.g., Meta, McKinsey, Deloitte, Amazon), include 1–2 questions inspired by its typical interview style. If not, ask questions relevant to the broader industry or functional context.

        Required Question Structure:
        1. Friendly introductory question to ask the candidate to introduce themselves
        2. Deep role-relevant question based on resume summary (domain expertise)
        3. Question on a different but relevant skill/area
        4. Advanced or strategic scenario to assess depth of understanding
        5. Real-world problem-solving or task-based question
        6. Question about best practices or optimization in the candidate's field
        7. Tools, platforms, or methodology familiarity question (based on resume summary)
        8. Troubleshooting or decision-making scenario
        9. Awareness of current trends or innovations in the industry
        10. Cultural fit, collaboration, or communication question

        Output only a valid JSON object exactly in the following format. Do not include any explanation or text outside the JSON:
        {{
            "greeting": "<warm greeting message>",
            "questions": [
                "<Question 1>",
                "<Question 2>",
                "... up to Question 10"
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
        ],
    )
    return LLMChain(llm=llm, prompt=prompt)


def generate_initial_question(
    job_role: str,
    company: str,
    resume_summary: str = None,
    years_of_experience: int = None,
    field: str = None,
):
    agent = create_dynamic_question_agent()
    return agent.invoke(
        {
            "job_role": job_role,
            "company": company,
            "resume_summary": resume_summary,
            "years_of_experience": years_of_experience,
            "field": field,
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
    return LLMChain(llm=llm, prompt=prompt)


def create_feedback_analysis_agent_paid():
    template = """
You are a seasoned interview evaluator with a focus on technical skills and career guidance. Based on the candidate's interview responses provided below as JSON, generate a detailed JSON report that strictly adheres to the PaidReview schema. Do not include any text or explanation outside of valid JSON. Even if the candidate's responses are brief, infer and provide realistic values based on subtle cues and overall expectations.
Also provide career path recommendations based on the candidate's performance and years of experience {years_of_experience} years.
Candidate Responses:
{responses}

Output the JSON object exactly in the following format:
{{
  "question_analysis": [
     {{
       "question": "<question text>",
       "question_id": "<unique identifier>",
       "quick_analysis": "<concise yet detailed evaluation, highlighting strengths, gaps, and improvement areas>"
     }}
  ],
  "performance_metrics": {{
     "critical_thinking": <number between 0 and 100>,
     "logical_reasoning": <number between 0 and 100>,
     "problem_solving": <number between 0 and 100>,
     "adaptability": <number between 0 and 100>,
     "creativity": <number between 0 and 100>,
     "foundational_knowledge": <number between 0 and 100>,
     "advanced_concepts": <number between 0 and 100>,
     "practical_application": <number between 0 and 100>,
     "articulation": <number between 0 and 100>,
     "technical_terms": <number between 0 and 100>,
     "active_listening": <number between 0 and 100>
  }},
  "career_path_recommendations": [
     {{
       "recommended_role": "<role_1>",
       "skill_match": <number between 0 and 100>,
       "skills": ["<skill1>", "<skill2>", "<skill3>"]
     }}
     {{
       "recommended_role": "<role_2>",
       "skill_match": <number between 0 and 100>,
       "skills": ["<skill1>", "<skill2>", "<skill3>"]
     }}
     {{
       "recommended_role": "<role_3>",
       "skill_match": <number between 0 and 100>,
       "skills": ["<skill1>", "<skill2>", "<skill3>"]
     }}
  ]
}}

If the candidate's responses are insufficient, infer and provide approximate realistic values rather than defaulting to 0 or "N/A".
    """
    prompt = PromptTemplate(
        template=template, input_variables=["responses", "years_of_experience"]
    )
    return LLMChain(llm=llm, prompt=prompt)


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
    agent = create_feedback_analysis_agent_paid()
    return agent.invoke({"responses": qaa, "years_of_experience": years_of_experience})


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
    return LLMChain(llm=llm, prompt=prompt)


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

    return LLMChain(llm=llm, prompt=prompt)


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
