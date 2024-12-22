from fastapi import FastAPI, Form, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from fastapi.responses import JSONResponse
from database import users_collection
import schemas, auth
import openai_utils
import json
from datetime import datetime
import time

logging.basicConfig(filename='app.log', level=logging.INFO)
logging.getLogger('pymongo').setLevel(logging.WARNING)

app = FastAPI()

origins = ["http://localhost:5173", "https://project-udaan-dev.netlify.app", "https://prepsom.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: introduce db to persist the above dict and also store some interview metadata for data visualization and analysis.
# TODO: life cycle of thread_assistants, delete entry once interview ends after capturing essential metadata.

@app.get("/")
async def health_check():
    return JSONResponse(content={"message": "Success."})

@app.post("/signup", response_model=schemas.UserOut)
async def signup(user: schemas.UserCreate = Form(...)):
    logging.info(user)
    # Check if user already exists
    existing_user = users_collection.find_one({ "email": user.email })
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered. It should be unique.")
    existing_user = users_collection.find_one({ "mobile_number": user.mobile_number})
    if existing_user:
        raise HTTPException(status_code=400, detail="Mobile Number already registered. It should be unique.")
    # Hash the password
    hashed_password = auth.hash_password(user.password)

    # create user thread and assitant
    thread_id, assistant_id = await openai_utils.create_user_thread_and_assistant(user.email, user.resume)
    
    user_data = {
        "full_name": user.full_name,
        "email": user.email,
        "hashed_password": hashed_password,
        "mobile_number": user.mobile_number,
        "institute": user.institute,
        "resume": f'{thread_id}_resume.pdf',
        "assistant_id": assistant_id,
        "thread_id": thread_id,
        "date_created": datetime.now()
    }
    
    # Save user in the database
    result = users_collection.insert_one(user_data)
    logging.info(result.inserted_id)
    # created_user = users_collection.find_one({"_id": result.inserted_id})

    access_token = auth.create_access_token(data={"sub": user.email})
    return JSONResponse(content={"message": access_token, "username": user.full_name.split(" ")[0]})

@app.post("/login", response_model=schemas.UserOut)
async def login(user: schemas.UserLogin):
    # Find user by email
    db_user = users_collection.find_one({"email": user.email})
    if not db_user or not auth.verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Create JWT token
    access_token = auth.create_access_token(data={"sub": db_user["email"]})
    return JSONResponse(content={"message": access_token, "email": db_user['email']})

@app.post("/interview_input", response_model=schemas.InterviewOut)
async def interview_input(interview_input: schemas.InterviewCreate, current_user: str = Depends(auth.get_current_user)):
    db_user = users_collection.find_one({"email": current_user})
    interview_data = {
        "job_role": interview_input.job_role,
        "industry": interview_input.industry,
        "overall_experience_yrs": interview_input.overall_experience_yrs,
        "date_created": datetime.now()
    }
    interview_id = int(time.time())
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{interview_id}": interview_data}})
    msgs = openai_utils.converse(db_user['thread_id'], db_user['assistant_id'],{"role": "user", "content": f"Add to the prompt - Customize the interview for Job Role - {interview_input.job_role}, Industry - {interview_input.industry}, Overall years of experince - {interview_input.overall_experience_yrs}"})
    return JSONResponse(content={"message": msgs, "interview_id": interview_id})

@app.get("/start_interview", response_model=schemas.Message)
async def start_interview(current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    msgs = openai_utils.converse(db_user['thread_id'], db_user['assistant_id'],{"role": "user", "content": "Start the interview."})
    return JSONResponse(content={"message": msgs})

@app.post("/interview_convo", response_model=schemas.Message)
async def interview_convo(response: schemas.UserResponse, current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    msgs = openai_utils.converse(db_user['thread_id'], db_user['assistant_id'],{"role": "user", "content": response.response})
    return JSONResponse(content={"message": msgs})

@app.get("/interview_feedback", response_model=schemas.InterviewFeedback)
async def interview_feedback(interview_id : int = Query(...), current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    msgs = openai_utils.converse(db_user['thread_id'], db_user['assistant_id'], {"role": "user", "content": """Evaluate the candidate's interview performance based on their user responses stored in the thread context. If the user has not given enough response, please rate accordingly. Provide feedback in the following JSON format:
    {
        "overall_score": <score from 1 to 10>,
        "speech": "<evaluation of communication clarity and fluency, rated 1 to 10>",
        "confidence": "<evaluation of the candidate's confidence, rated 1 to 10>",
        "technical_skills": "<evaluation of technical skills based on responses, rated 1 to 10>",
        "areas_of_improvement": "<specific and actionable suggestions for improvement>"
    }
    Focus on providing constructive, actionable feedback for each area. Be objective and concise. Output in JSON format only."""})
    feedback = json.loads(msgs)
    feedback['timestamp'] = datetime.now() 
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{interview_id}.scores": feedback}})
    return JSONResponse(content=json.loads(msgs))

@app.post("/user_feedback", response_model=schemas.Message)
async def user_feedback(feedback: schemas.Feedback, interview_id : int = Query(...), current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    user_feedback = {
        "overall_experience": feedback.overall_experience,
        "recommend_score": feedback.recommend_score,
        "pay_for_report": feedback.pay_for_report,
        "pay_price": feedback.pay_price,
        "suggestions": feedback.suggestions,
        "timestamp": datetime.now()
    }
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{interview_id}.feedback": user_feedback}})
    return JSONResponse(content={"message": "Thank you for your valuable feedback!!!"})

# @app.get("/.well-known/pki-validation/{filename}", response_class=PlainTextResponse)
# async def auth_file(filename: str):
#     file_path = Path('auth_file') / filename
#     print(file_path)
#     content = ""
#     if not file_path.exists() or not file_path.is_file():
#         raise HTTPException(status_code=404, detail="File not found")
#     try:
#         with open(file_path, "r", encoding="utf-8") as file:
#             content = file.read()
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error reading file {str(e)}")
#     return content


# Protected Route
@app.get("/getCurrentUser")
async def protected_route(current_user: str = Depends(auth.get_current_user)):
    return {"message": f"Welcome, {current_user}!"}