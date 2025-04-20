import os
import logging
from fastapi import FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_community.llms import OpenAI
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain
import json

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()

# Configure Logging
logging.basicConfig(level=logging.INFO)

# Initialize Free OpenAI model (for general use)
llm = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Paid OpenAI model (ensure you have access to GPT-4 or similar)
paid_llm = OpenAI(
    temperature=0.7,
    model_name="gpt-4",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

# Initialize Memory
memory = ConversationBufferMemory()


# Pydantic Models
class InterviewInput(BaseModel):
    job_role: str
    company: str


class InterviewResponse(BaseModel):
    responses: list  # List of answers


class FeedbackInput(BaseModel):
    qaa: str


# Generate initial questions agent
# def create_dynamic_question_agent():
#     template = """
#         Greet the candidate warmly in real time. Start by asking an introductory question that prompts the candidate to introduce themselves.
#         Then, generate 9 additional unique and dynamic interview questions for a candidate applying for {job_role} at {company} in {field} and based on experience {years_of_experience} years.
#         The questions should explore the candidate's skills, experience, cultural fit and also candidate's resume {resume}.

#         Return a JSON object in the following format (with no placeholder text):
#         {{
#         "greeting": "Your warm greeting message",
#         "questions": [
#             "Introductory question: Ask the candidate to introduce themselves.",
#             "Question 2",
#             "Question 3",
#             "Question 4",
#             "Question 5",
#             "Question 6",
#             "Question 7",
#             "Question 8",
#             "Question 9",
#             "Question 10"
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


# def create_dynamic_question_agent():
#     template = """
#         Greet the candidate warmly in real time. Start by asking an introductory question that prompts the candidate to introduce themselves.

#         Then, generate 9 additional *unique and well-structured* interview questions for a candidate applying for the role of {job_role} at {company} in the field of {field}, with {years_of_experience} years of experience.

#         The questions should be *balanced* as follows:
#         - At least *three* deeply *technical* questions that test core expertise based on the candidate's resume ({resume}).
#         - The remaining *six* should assess *problem-solving, frameworks/tools proficiency, real-world application, best practices, debugging, and cultural fit*.

#         Structure:
#         1. *(Introductory Question)* Ask the candidate to introduce themselves.
#         2. *(Technical Question 1)* In-depth technical question testing core expertise.
#         3. *(Technical Question 2)* Another technical question, focusing on a different key skill.
#         4. *(Technical Question 3)* Advanced or specialized technical scenario.
#         5. *(Problem-Solving Scenario)* Real-world problem the candidate might face in this role.
#         6. *(Best Practices & Optimization)* Question assessing industry best practices.
#         7. *(Frameworks & Tools)* Evaluates proficiency with key technologies mentioned in the resume.
#         8. *(Debugging & Edge Cases)* A scenario requiring troubleshooting and debugging skill in particular job field based on resume.
#         9. *(New Trends & Innovation)* Checks awareness of emerging trends in the field.
#         10. *(Cultural Fit & Teamwork)* Evaluates how well the candidate aligns with company values and teamwork skills.

#         Return a JSON object in the following format (with no placeholder text):
#         {{
#         "greeting": "Your warm greeting message",
#         "questions": [
#             "Introductory question: Ask the candidate to introduce themselves.",
#             "Question 2: (Technical question testing deep expertise)",
#             "Question 3: (Technical question on a different skill)",
#             "Question 4: (Advanced or specialized technical scenario)",
#             "Question 5: (Problem-solving scenario relevant to the job role)",
#             "Question 6: (Best practices & optimization techniques)",
#             "Question 7: (Frameworks/tools proficiency)",
#             "Question 8: (Debugging & edge case handling)",
#             "Question 9: (New trends in the field & future-proofing knowledge)",
#             "Question 10: (Cultural fit, teamwork, or leadership skills)"
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
        Greet the candidate warmly in real time. Start by asking a friendly, conversational introductory question that prompts the candidate to introduce themselves.

        Then, generate 9 additional unique and well-structured interview questions for a candidate applying for the role of {job_role} at {company} in the field of {field}, with {years_of_experience} years of experience.

        The questions should be balanced as follows:
        - At least three deeply technical questions that test core expertise based on the candidate's resume ({resume}).
        - The remaining six should assess problem-solving, frameworks/tools proficiency, real-world application, best practices, debugging, and cultural fit.

        Structure:
        1. Ask the candidate to introduce themselves in a natural, friendly way.
        2. Ask a specific, deeply technical question based on the resume to assess core expertise.
        3. Ask a technical question focused on a different relevant skill or area of expertise.
        4. Pose an advanced or specialized technical scenario to assess depth of knowledge.
        5. Present a realistic problem-solving scenario they might face in this role.
        6. Ask a question that assesses understanding of industry best practices or optimization strategies.
        7. Evaluate proficiency with key frameworks/tools mentioned in the resume.
        8. Present a debugging or edge-case troubleshooting scenario relevant to the job field.
        9. Ask a question that explores knowledge of current trends or innovations in the field.
        10. Ask a question that evaluates cultural fit, communication, or teamwork skills in the workplace.

        Return a JSON object in the following format (with no placeholder text):
        {{
        "greeting": "Your warm greeting message",
        "questions": [
            "Conversational introductory question...",
            "Fully-formed technical question 1...",
            "Fully-formed technical question 2...",
            "Advanced technical scenario question...",
            "Real-world problem-solving scenario...",
            "Best practices and optimization question...",
            "Frameworks/tools proficiency question...",
            "Debugging or edge case handling scenario...",
            "Trends/innovation awareness question...",
            "Cultural fit or teamwork question..."
        ]
        }}
        """
    prompt = PromptTemplate(
        template=template,
        input_variables=[
            "job_role",
            "company",
            "resume",
            "years_of_experience",
            "field",
        ],
    )
    return LLMChain(llm=llm, prompt=prompt)


def generate_initial_question(
    job_role: str,
    company: str,
    resume: str = None,
    years_of_experience: int = None,
    field: str = None,
):
    agent = create_dynamic_question_agent()
    return agent.invoke(
        {
            "job_role": job_role,
            "company": company,
            "resume": resume,
            "years_of_experience": years_of_experience,
            "field": field,
        }
    )


# def create_feedback_analysis_agent():
#     template = """
# You are a highly experienced interview evaluator. Based on the candidate's interview responses provided below as JSON, produce a detailed and realistic JSON report that strictly adheres to the FreeReview schema. Even if the responses are brief, infer and provide non-default realistic values based on subtle cues and general expectations for a good candidate. Do not include any text or explanation outside of valid JSON.

# Candidate Responses:
# {responses}

# Output the JSON object exactly in the following format:
# {{
#   "overall_score": <number between 0 and 100>,
# #   "overall_summary": "<detailed summary of overall performance>",

#   "overall_summary": "<a concise 2-3 sentence summary of your overall performance, addressing you directly. For example, 'You demonstrated a strong grasp of Python fundamentals and proficiency with frameworks such as Django. Your communication was clear, though enhancing your active listening could further improve your performance. Your time management was commendable, yet refining your conceptual understanding may lead to even better outcomes.' and different for different role based on candidates interview analysis>",
#   "skill_analysis": {{
#      "communication_skills": {{
#          "clarity": <number between 0 and 100>,
#          "articulation": <number between 0 and 100>,
#          "active_listening": <number between 0 and 100>
#      }},
#      "conceptual_understanding": {{
#          "fundamental_concepts": <number between 0 and 100>,
#          "theoretical_application": <number between 0 and 100>,
#          "analytical_reasoning": <number between 0 and 100>
#      }},
#      "speech_analysis": {{
#          "avg_filler_words_used": <integer>,
#          "avg_confidence_level": "<High|Medium|Low>",
#          "avg_fluency_rate": <number between 0 and 100>
#      }},
#      "time_management": {{
#          "average_response_time": "<string, e.g., '45 seconds'>",
#          "question_completion_rate": <number between 0 and 100>
#      }}
#   }},
#   "strengths_and_weaknesses": [
#      {{
#         "type": "strength",
#         "title": "<title for strength>",
#         "description": "<description of the strength>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for weakness>",
#         "description": "<description of the weakness>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for additional weakness>",
#         "description": "<description of the additional weakness>"
#      }}
#   ]
# }}

# If the candidate's responses are insufficient, infer and provide approximate realistic values based on the overall context rather than defaulting to 0 or "N/A".
#     """
#     prompt = PromptTemplate(template=template, input_variables=["responses"])
#     return LLMChain(llm=llm, prompt=prompt)


# def create_feedback_analysis_agent():
#     template = """
# You are a highly experienced interview evaluator. Based on the candidate's interview responses provided below as JSON, generate a detailed and realistic JSON report that strictly follows the FreeReview schema.
# *Key Conditions:*
# - *If the candidate provided fewer than 4 responses, do not generate feedback. Instead, return a message directing them back to the landing page.*
# - *Overall score and summary must be categorized based on the number of responses:*
#   - *Low* (≤ 40%) → 4 responses.
#   - *Medium* (50-70%) → 5-7 responses.
#   - *High* (80-100%) → 8-10 responses.

# If fewer than 4 responses are provided, return this exact JSON response:

# Ensure that:
# 1. The overall score is calculated realistically, factoring in both answered and unanswered questions.
# 2. The question completion rate is accurately derived from the number of responses provided.
# 3. The overall summary is tailored based on the responses, avoiding generic statements like "You're good at XYZ technology" unless explicitly supported.
# 4. Always generate exactly three strengths and three weaknesses, even if inferred from minimal responses.
# 5. *If a response is missing for any question, infer a likely transcript and relevant parameters based on the question type, but do not overinflate performance scores. Ensure every question has a transcript, fluency score, confidence score, filler words, response time, and clarity score.*

# Candidate Responses:
# {responses}

# Output the JSON object exactly in the following format:
# {{
#   "overall_score": <realistic number between 0 and 100, reflecting completeness and performance>,
#   "overall_summary": "<A concise 2-3 sentence summary addressing the candidate directly, highlighting key strengths and areas for improvement based on responses>",

#   "skill_analysis": {{
#      "communication_skills": {{
#          "clarity": <number between 0 and 100>,
#          "articulation": <number between 0 and 100>,
#          "active_listening": <number between 0 and 100>
#      }},
#      "conceptual_understanding": {{
#          "fundamental_concepts": <number between 0 and 100>,
#          "theoretical_application": <number between 0 and 100>,
#          "analytical_reasoning": <number between 0 and 100>
#      }},
#      "speech_analysis": {{
#          "avg_filler_words_used": <integer>,
#          "avg_confidence_level": "<High|Medium|Low>",
#          "avg_fluency_rate": <number between 0 and 100>
#      }},
#      "time_management": {{
#          "average_response_time": "<string, e.g., '45 seconds'>",
#          "question_completion_rate": <realistic number between 0 and 100, based on answered questions>
#      }}
#   }},
#   "strengths_and_weaknesses": [
#      {{
#         "type": "strength",
#         "title": "<title for strength>",
#         "description": "<description of the strength>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<title for additional strength>",
#         "description": "<description of the additional strength>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<title for another strength>",
#         "description": "<description of the strength>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for weakness>",
#         "description": "<description of the weakness>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for additional weakness>",
#         "description": "<description of the additional weakness>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for another weakness>",
#         "description": "<description of the weakness>"
#      }}
#   ]
# }}

# If most responses are missing, infer realistic approximate values based on context, ensuring every question has a complete set of transcript data and evaluation metrics, but do not overinflate scores.
#     """
#     prompt = PromptTemplate(template=template, input_variables=["responses"])
#     return LLMChain(llm=llm, prompt=prompt)


# def create_feedback_analysis_agent():
#     template = """
# You are a highly experienced interview evaluator. Based on the candidate's interview responses provided below as JSON, generate a detailed and realistic JSON report that strictly follows the FreeReview schema.

# Ensure that:
# 1. The overall score is calculated realistically, factoring in both answered and unanswered questions.
# 2. The question completion rate is accurately derived from the number of responses provided.
# 3. The overall summary is tailored based on the responses, avoiding generic statements like "You're good at XYZ technology" unless explicitly supported.
# 4. Always generate exactly three strengths and three weaknesses, even if inferred from minimal responses.
# 5. *If a response is missing for any question, infer a likely transcript and relevant parameters based on the question type, but do not overinflate performance scores. Ensure every question has a transcript, fluency score, confidence score, filler words, response time, and clarity score.*

# Candidate Responses:
# {responses}

# Output the JSON object exactly in the following format:
# {{
#   "overall_score": <realistic number between 0 and 100, reflecting completeness and performance>,
#   "overall_summary": "<A concise 2-3 sentence summary addressing the candidate directly, highlighting key strengths and areas for improvement based on responses>",

#   "skill_analysis": {{
#      "communication_skills": {{
#          "clarity": <number between 0 and 100>,
#          "articulation": <number between 0 and 100>,
#          "active_listening": <number between 0 and 100>
#      }},
#      "conceptual_understanding": {{
#          "fundamental_concepts": <number between 0 and 100>,
#          "theoretical_application": <number between 0 and 100>,
#          "analytical_reasoning": <number between 0 and 100>
#      }},
#      "speech_analysis": {{
#          "avg_filler_words_used": <integer>,
#          "avg_confidence_level": "<High|Medium|Low>",
#          "avg_fluency_rate": <number between 0 and 100>
#      }},
#      "time_management": {{
#          "average_response_time": "<string, e.g., '45 seconds'>",
#          "question_completion_rate": <realistic number between 0 and 100, based on answered questions>
#      }}
#   }},
#   "strengths_and_weaknesses": [
#      {{
#         "type": "strength",
#         "title": "<title for strength>",
#         "description": "<description of the strength>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<title for additional strength>",
#         "description": "<description of the additional strength>"
#      }},
#      {{
#         "type": "strength",
#         "title": "<title for another strength>",
#         "description": "<description of the strength>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for weakness>",
#         "description": "<description of the weakness>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for additional weakness>",
#         "description": "<description of the additional weakness>"
#      }},
#      {{
#         "type": "weakness",
#         "title": "<title for another weakness>",
#         "description": "<description of the weakness>"
#      }}
#   ]
# }}

# If most responses are missing, infer realistic approximate values based on context, ensuring every question has a complete set of transcript data and evaluation metrics, but do not overinflate scores.
#     """
#     prompt = PromptTemplate(template=template, input_variables=["responses"])
#     return LLMChain(llm=llm, prompt=prompt)


def create_feedback_analysis_agent():

    try:
        responses_dict = json.loads(responses)
    except Exception:
        responses_dict = {}

    total_questions = len(responses_dict)
    answered_questions = sum(1 for answer in responses_dict.values() if answer.strip())

    template = """
You are a highly experienced interview evaluator. Based on the candidate's interview responses provided below as JSON, generate a detailed and realistic JSON report that strictly follows the FreeReview schema.

Important details:
1. Each answered question should be evaluated individually and assigned a score out of 10 based on quality, clarity, and relevance. Unanswered questions receive a score of 0.
2. The overall score is the sum of the individual question scores.
3. The overall summary should directly reflect the analysis of each answered question and include specific, actionable feedback.
4. The skill analysis (communication_skills, conceptual_understanding, speech_analysis, time_management) must also account for the ratio of answered questions.
5. Always generate exactly three strengths and three weaknesses based on the candidate's responses.
6. Include the ratio of answered questions to total questions in the time_management analysis ("question_completion_rate") using the following data:
   - Total Questions: {total_questions}
   - Answered Questions: {answered_questions}
7. Use the candidate responses below to infer and provide specific, actionable feedback for each area.

Candidate Responses:
{responses}

Output the JSON object exactly in the following format:
{{
  "overall_score": <realistic number between 0 and {max_score}>,
  "overall_summary": "<A concise 2-3 sentence summary addressing the candidate directly, highlighting key strengths and areas for improvement>",
  
  "skill_analysis": {{
     "communication_skills": {{
         "clarity": <number between 0 and 100 scaled by answered ratio>,
         "articulation": <number between 0 and 100 scaled by answered ratio>,
         "active_listening": <number between 0 and 100 scaled by answered ratio>
     }},
     "conceptual_understanding": {{
         "fundamental_concepts": <number between 0 and 100 scaled by answered ratio>,
         "theoretical_application": <number between 0 and 100 scaled by answered ratio>,
         "analytical_reasoning": <number between 0 and 100 scaled by answered ratio>
     }},
     "speech_analysis": {{
         "avg_filler_words_used": <integer>,
         "avg_confidence_level": "<High|Medium|Low>",
         "avg_fluency_rate": <number between 0 and 100 scaled by answered ratio>
     }},
     "time_management": {{
         "average_response_time": "<string, e.g., '45 seconds'>",
         "question_completion_rate": <percentage representing answered questions over total (0 to 100)>
     }}
  }},
  "strengths_and_weaknesses": [
     {{
        "type": "strength",
        "title": "<title for strength>",
        "description": "<description of the strength>"
     }},
     {{
        "type": "strength",
        "title": "<title for additional strength>",
        "description": "<description of the additional strength>"
     }},
     {{
        "type": "strength",
        "title": "<title for another strength>",
        "description": "<description of the strength>"
     }},
     {{
        "type": "weakness",
        "title": "<title for weakness>",
        "description": "<description of the weakness>"
     }},
     {{
        "type": "weakness",
        "title": "<title for additional weakness>",
        "description": "<description of the additional weakness>"
     }},
     {{
        "type": "weakness",
        "title": "<title for another weakness>",
        "description": "<description of the weakness>"
     }}
  ]
}}
"""
    # Fill in the placeholders in the template
    filled_template = template.format(
        responses=responses,
        total_questions=total_questions,
        answered_questions=answered_questions,
        max_score=answered_questions * 10,
    )

    prompt = PromptTemplate(template=filled_template, input_variables=[])
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


def generate_feedback(qaa: str):
    agent = create_feedback_analysis_agent()
    return agent.invoke({"responses": qaa})


def generate_feedback_paid(qaa: str, years_of_experience: int):
    agent = create_feedback_analysis_agent_paid()
    return agent.invoke({"responses": qaa, "years_of_experience": years_of_experience})


# API Endpoint to Start Interview
@app.post("/start_interview")
def start_interview(interview_input: InterviewInput):
    question_agent = create_dynamic_question_agent()
    response = question_agent.invoke(interview_input.dict())
    return response  # Returns greeting and 10 questions


@app.post("/get_interview_feedback")
def get_interview_feedback(feedback_input: FeedbackInput):
    feedback_agent = create_feedback_analysis_agent()
    response = feedback_agent.invoke({"responses": feedback_input.qaa})
    return response


# Log success
logging.info("Interview AI API is up and running successfully.")
