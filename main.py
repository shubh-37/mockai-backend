from fastapi import FastAPI, Form, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from fastapi.responses import JSONResponse
from database import users_collection, company_collection
import schemas, auth
import openai_utils
import json
from datetime import datetime
import time
from typing import List

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

@app.get("/")
async def health_check():
    return JSONResponse(content={"message": "Success."})

@app.post("/signup", response_model=schemas.UserOut)
async def signup(user: schemas.UserCreate = Form(...)):
    logging.info(f"New User Signup : {user.full_name} - {user.email} ")
    # Check if user already exists
    existing_user = users_collection.find_one({ "email": user.email })
    if existing_user:
        logging.info("Email already registered. It should be unique.")
        raise HTTPException(status_code=422, detail="Email already registered. It should be unique.")
    # Hash the password
    hashed_password = auth.hash_password(user.password)
    # create user thread and assitant
    thread_id, assistant_id, vs_id = openai_utils.create_user_thread_and_assistant(user.email)
    current_time = datetime.utcnow()
    user_data = {
        "full_name": user.full_name,
        "email": user.email,
        "hashed_password": hashed_password,
        "assistant_id": assistant_id,
        "thread_id": thread_id,
        "vector_store_id": vs_id,
        "date_created": current_time,
        "last_updated": current_time,
        "last_loggedin": current_time,
        "interviews": {}
    }
    # Save user in the database
    result = users_collection.insert_one(user_data)
    logging.info(result.inserted_id)
    access_token = auth.create_access_token(data={"sub": user.email})
    return JSONResponse(content={"message": access_token, "username": user.full_name.split(" ")[0]})

@app.patch("/profile", response_model=schemas.Message)
async def update_profile(profile: schemas.UserProfile = Form(...), current_user: str = Depends(auth.get_current_user)):
    logging.info(f"Update profile: {profile}")
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if profile.mobile_number is not None:
        existing_user = users_collection.find_one({ "mobile_number": profile.mobile_number, "email": { "$ne": current_user }})
        if existing_user:
            logging.info("Mobile Number already registered. It should be unique.")
            raise HTTPException(status_code=422, detail="Mobile Number already registered. It should be unique.")
    update_data = json.loads(profile.model_dump_json(exclude_unset=True, exclude={"resume", "email", "password"}))
    if profile.password is not None:
        update_data['hashed_password'] = auth.hash_password(profile.password)
    if profile.resume is not None:
        try:
            if db_user.get('resume_file_id') is not None:
                openai_utils.delete_file(db_user['vector_store_id'], db_user['resume_file_id'])
            file_id = await openai_utils.add_file_to_vs(current_user, profile.resume, db_user['vector_store_id'])
            update_data['resume_file_id'] = file_id
        except Exception as e:
            raise HTTPException(status_code=400, detail="Error updating profile. Try again after sometime.")
    update_data['last_updated'] = datetime.utcnow()
    result = users_collection.update_one({"_id": db_user['_id']}, {"$set": update_data})
    if result.modified_count == 0:
        logging.info("Profile not updated. Try again.")
        raise HTTPException(status_code=400, detail="Profile not updated. Try again.")

    return JSONResponse(content={"message": "Profile updated successfully."})

@app.get("/profile", response_model=schemas.UserProfile)
async def get_profile(current_user: str = Depends(auth.get_current_user)):
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    profile_info = {
        "full_name": db_user.get("full_name"),
        "email": db_user.get("email"),
        "mobile_number": db_user.get("mobile_number"),
        "institute": db_user.get("institute"),
        "resume": None,
        "yrs_of_exp": db_user.get("yrs_of_exp"),
        "job_role": db_user.get("job_role"),
        "company": db_user.get("company"),
        "password": None,
        "resume": True if db_user.get("resume_file_id") else False
    }
    return JSONResponse(content=profile_info)

@app.get("/companies", response_model=List[str])
async def get_companies():
    db_companies = company_collection.find({}, { "name": 1, "_id": 0 })
    companies = []
    for db_company in db_companies:
        companies.append(db_company["name"])
    return JSONResponse(content=companies)

@app.post("/login", response_model=schemas.UserOut)
async def login(user: schemas.UserLogin):
    # Find user by email
    db_user = users_collection.find_one({"email": user.email})
    if not db_user or not auth.verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Create JWT token
    access_token = auth.create_access_token(data={"sub": db_user["email"]})
    users_collection.update_one({"_id": db_user['_id']}, {"$set": { "last_loggedin": datetime.utcnow() }})
    return JSONResponse(content={"message": access_token, "username": db_user['full_name'].split(" ")[0]})

@app.get("/start_interview", response_model=schemas.InterviewOut)
async def start_interview(current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    interview_data = {
        "timestamp": datetime.utcnow(),
        "job_role": db_user['job_role'], 
        "company": db_user['company'], 
        "difficulty": "Easy" if db_user['yrs_of_exp'] <=2 else ("Intermediate" if db_user['yrs_of_exp'] <=5 else "Advanced")
    }
    company_logo = company_collection.find_one({"name": db_user["company"]}, {"logo_link": 1, "_id": 0})
    if company_logo is None:
        company_logo = "Prepsom"
    else:
        company_logo = company_logo['logo_link']
    msgs = openai_utils.start_interview(db_user['thread_id'], db_user['assistant_id'],interview_data, db_user["full_name"])
    interview_id = int(time.time())
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{interview_id}": interview_data}})
    return JSONResponse(content={"questions": json.loads(msgs)['questions'], "interview_id": interview_id, "company_logo": company_logo})

@app.post("/submit_interview", response_model=schemas.Message)
async def interview_convo(response: schemas.InterviewResponse, current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if db_user.get("interviews").get(f"{response.interview_id}") is None:
        raise HTTPException(status_code=404, detail=f"Interview not started with id {response.interview_id}")
    qaa_list = [qaa.model_dump() for qaa in response.qaa]
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{response.interview_id}.qaa": qaa_list}})
    return JSONResponse(content={"message": "Interview submitted successfully."})

@app.get("/interview_feedback", response_model=schemas.InterviewFeedback)
async def interview_feedback(interview_id : int = Query(...), current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if db_user.get("interviews").get(f"{interview_id}") is None:
        raise HTTPException(status_code=404, detail=f"Interview not started with id {interview_id}")
    if db_user.get("interviews").get(f"{interview_id}").get("qaa") is None:
        raise HTTPException(status_code=404, detail=f"Interview not submitted with id {interview_id}")
    if db_user.get("interviews").get(f"{interview_id}").get("scores"):
        return JSONResponse(content=db_user.get("interviews").get(f"{interview_id}").get("scores"))
    msgs = openai_utils.get_interview_feedback(db_user["thread_id"], db_user["assistant_id"], db_user["interviews"][f"{interview_id}"]["qaa"])
    feedback = json.loads(msgs)
    users_collection.update_one({'_id': db_user['_id']}, {"$set": {f"interviews.{interview_id}.scores": feedback}})
    return JSONResponse(content=feedback)

@app.post("/user_feedback", response_model=schemas.Message)
async def user_feedback(feedback: schemas.Feedback, interview_id : int = Query(...), current_user: str = Depends(auth.get_current_user)):
    # get thread_id and assistant_id from db
    db_user = users_collection.find_one({"email": current_user})
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
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

# Protected Route
@app.get("/getCurrentUser")
async def protected_route(current_user: str = Depends(auth.get_current_user)):
    return {"message": f"Welcome, {current_user}!"}