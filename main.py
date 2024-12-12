from fastapi import FastAPI, UploadFile, Body, File, Form, Depends, Request, Query, HTTPException
from openai import OpenAI
from pydantic import BaseModel
import os
from fastapi.middleware.cors import CORSMiddleware
import logging
from typing import Dict
import openai
from fastapi.responses import JSONResponse
import aiofiles
from pathlib import Path
from fastapi.responses import PlainTextResponse
import json

logging.basicConfig(filename='app.log', level=logging.INFO)

app = FastAPI()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

origins = ["http://localhost:5173", "https://project-udaan-dev.netlify.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

thread_assistants: Dict[str, str] = {} 
# TODO: introduce db to persist the above dict and also store some interview metadata for data visualization and analysis.
# TODO: life cycle of thread_assistants, delete entry once interview ends after capturing essential metadata.

def upload_file_for_thread(thread_id):
    
    response = openai_client.files.create(
        file=open(os.path.join('tmp_files', f'{thread_id}_resume.pdf'), 'rb'),
        purpose='assistants'
    )
    # print(response)
    # TODO: delete temp resume file
    return response.id

def create_vector_store(thread_id):
    response = openai_client.beta.vector_stores.create(
        name=f"Vector Store for {thread_id}",
        # description=f"Resume for user id: {thread_id}."
    )
    return response.id

def add_file_to_vector_store(vector_store_id, file_id):
    openai_client.beta.vector_stores.file_batches.create_and_poll(
        vector_store_id=vector_store_id,
        file_ids=[file_id]
    )

def create_thread_specific_assistant(thread_id, vector_store_id, job_role, industry):
    assistant = openai_client.beta.assistants.create(
        name="Interview Companion",
            # TODO: explore timer in chatgpt
            # TODO: Improve promts
            instructions=f"""You are an AI interviewer designed to evaluate candidates for specific job roles based on their resume, job role, and job description. Your goal is to conduct a realistic and structured mock interview using the provided inputs: Job Role ({job_role}) and Industry ({industry}). Use the candidate's resume (stored in the vector store) to tailor your questions. Follow these evaluation criteria and guidelines:
            Interview Sections:
            1. Personality Assessment (25% weight):
                - Ask questions about the candidate's background, motivations, and interpersonal skills.
                - Evaluate their confidence, communication clarity, and articulation.
            2. Technical and Industry-Relevant Assessment (25% weight):
                - Create questions aligned with the key skills, knowledge, and trends outlined in the job description.
                - Test the candidate's understanding of technical concepts and practical applications.
            3. Resume-Based Questions (25% weight):
                - Ask specific questions about the candidate's past experiences, achievements, and roles mentioned in their resume.
                - Evaluate their ability to relate past experiences to the requirements of the job role.
            4. Adaptability and Critical Thinking (25% weight):
                - Pose situational or behavioral questions to assess problem-solving skills and adaptability.
            Interview Guidelines:
            1. Keep the interview realistic and professional.
            2. The interview duration is 5 minutes.
            3. Begin asking questions only when the user says "Start the interview".
            4. Ask one question at a time and wait for the candidate's response before proceeding.
            5. Use the candidate's resume and job description context to ask customized and meaningful questions.
            6. End the interview politely after 5 minutes.
            7. Start the interview by asking the candidate to give introduction followed by why they chose to be in this particular field. Then ask technical questions that the candidate might have studied to pursue the profession followed by what you feel is best.
            8. Don't give feedback on the questions answered while the 
            9. Ask learnings from the project mentioned in the resume
            10. Don't ask questions together, ask one by one. don't combine 2 questions together.
            11. ask 5 questions, instead of timer. 
            Leverage context from the thread to craft better and more specific follow-up questions. Prioritize engaging, insightful, and job-relevant inquiries throughout the interview.""",
            model="gpt-4-turbo",
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
    )
    return assistant

def converse(thread_id, input_context):
        """
        Sends user input to OpenAI and gets a response.
        """
        try:
            message = openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role=input_context["role"],
                content=input_context["content"],
            )
            run = openai_client.beta.threads.runs.create_and_poll(
                thread_id=thread_id,
                assistant_id=thread_assistants[thread_id],
            )
            logging.info(run)
            # List messages in the thread
            messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
            # Display the assistant's response
            msgs = []
            for msg in messages:
                if msg.role == "assistant":
                    logging.info(f"Assistant: {msg.content}")
                    msgs.append(msg.content)
            return msgs[0][0].text.value
        except Exception as e:
            logging.info(f"Error communicating with OpenAI API: {e}")
            return "I'm sorry, I couldn't process that."

# Dependency to extract headers
async def get_headers(
    thread_id: str
):
    return {"thread_id": thread_id}

class Response(BaseModel):
    response: str

class InterviewFeedback(BaseModel):
    overall_score: float
    speech: str
    confidence: str
    technical_skills: str
    areas_of_imporvements: str

@app.get("/")
async def health_check():
    return JSONResponse(content={"message": "Success."})

@app.post("/submit_user_data")
async def submit_user_data(job_role: str = Form(...), industry: str = Form(...), resume: UploadFile = File(...)):
    logging.info("Request received for submitting user data.")
    # TODO: associate thread with user_id when we introduce sessions (login)
    user_thread = openai_client.beta.threads.create()
    async with aiofiles.open(os.path.join('tmp_files', f'{user_thread.id}_resume.pdf'), 'wb') as out_file:
        while content := await resume.read(1024):  # async read chunk
            await out_file.write(content)  # async write chunk
    # TODO: validate resume whether it is not a malicious file
    file_id = upload_file_for_thread(user_thread.id)
    vector_store_id = create_vector_store(user_thread.id)
    add_file_to_vector_store(vector_store_id, file_id)
    assistant = create_thread_specific_assistant(user_thread.id, vector_store_id, job_role, industry)
    thread_assistants[user_thread.id] = assistant.id
    return JSONResponse(content={"message": "User Data submitted successfully.", "thread_id": user_thread.id})

@app.get("/start_interview")
async def start_interview(thread_id: str = Query(...)):
    msgs = converse(thread_id, {"role": "user", "content": "Start the interview."})
    return JSONResponse(content={"message": msgs, "thread_id": thread_id})

@app.post("/interview_convo")
async def interview_convo(response: Response, thread_id: str = Query(...)):
    msgs = converse(thread_id, {"role": "user", "content": response.response})
    return JSONResponse(content={"message": msgs, "thread_id": thread_id})

@app.get("/interview_feedback")
async def interview_feedback(thread_id: str = Query(...)):
    msgs = converse(thread_id, {"role": "user", "content": """Evaluate the candidate's interview performance based on their user responses stored in the thread context. If the user has not given enough response, please rate accordingly. Provide feedback in the following JSON format:
    {
        "overall_score": <score from 1 to 10>,
        "speech": "<evaluation of communication clarity and fluency, rated 1 to 10>",
        "confidence": "<evaluation of the candidate's confidence, rated 1 to 10>",
        "technical_skills": "<evaluation of technical skills based on responses, rated 1 to 10>",
        "areas_of_improvement": "<specific and actionable suggestions for improvement>"
    }
    Focus on providing constructive, actionable feedback for each area. Be objective and concise. Output in JSON format only."""})
    return JSONResponse(content={"message": json.loads(msgs), "thread_id": thread_id})

@app.get("/.well-known/pki-validation/{filename}", response_class=PlainTextResponse)
async def auth_file(filename: str):
    file_path = Path('auth_file') / filename
    print(file_path)
    content = ""
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file {str(e)}")
    return content

