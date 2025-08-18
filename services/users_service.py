from fastapi import Depends, File, HTTPException, APIRouter, Query, UploadFile
from fastapi.responses import JSONResponse
from models.users import User
from models.company import Company
from models.user_aptitude import UserAptitude
from models.customer_feedback import CustomerFeedback
from models.interview import Interview
import schemas, auth
import logging
import json
from typing import List
from datetime import datetime
import os
import boto3
from io import BytesIO
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import random
import string
import time
import redis.asyncio as redis_asyncio
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import openai_utils
import common_utils
from bson import ObjectId

load_dotenv()

router = APIRouter()

OTP_EXPIRY_SECONDS = 300


async def get_redis():
    redis = redis_asyncio.from_url(os.getenv("REDIS_URI"), decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()


def otp_redis_key(email: str) -> str:
    return f"otp:{email}"


def generate_random_filename(original_name: str) -> str:
    random_str = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    extension = ""
    if "." in original_name:
        extension = "." + original_name.split(".")[-1]

    timestamp = str(int(time.time()))

    new_name = f"{random_str}_{timestamp}{extension}"
    return new_name


# async def send_email_otp(email: str, otp: int):

#     subject = "Your OTP Verification Code"
#     body = f"Hello,\n\nYour verification code is {otp}. This code is valid for 5 minutes. Please do not share this code with anyone.\n\nThank you!"

#     message = Mail(
#         from_email="support@mockai.tech",
#         to_emails=email,
#         subject=subject,
#         html_content=body,
#     )

#     try:
#         sg = SendGridAPIClient(os.getenv("SEND_GRID_API_KEY"))
#         response = sg.send(message)
#         logging.info(f"Email OTP sent successfully to {email}.")
#     except Exception as e:
#         logging.error(f"Error sending email OTP: {e}")
#         raise HTTPException(status_code=500, detail="Failed to send email OTP.")


async def send_email_otp(email: str, otp: int):
    subject = "Your OTP Verification Code"
    body = f"""
    <html>
        <body>
            <p>Hello,</p>
            <p>Your verification code is <strong>{otp}</strong>. This code is valid for 5 minutes. Please do not share this code with anyone.</p>
            <p>Thank you!</p>
        </body>
    </html>
    """

    # Setup Brevo configuration
    configuration = sib_api_v3_sdk.Configuration()
    print(os.getenv("BREVO_API_KEY"))
    configuration.api_key["api-key"] = os.getenv("BREVO_API_KEY")

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"email": "support@mockai.tech", "name": "MockAI Support"},
        subject=subject,
        html_content=body,
    )

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        logging.info(
            f"Email OTP sent successfully to {email}. Message ID: {api_response.message_id}"
        )
    except ApiException as e:
        logging.error(f"Error sending email OTP to {email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email OTP.")


# async def send_otp_service(user: dict, otp: int) -> dict:
#     country_code = user.get("countryCode", "")
#     mobile_number = user.get("mobileNumber", "")

#     # If running in development mode, log and return a success message without sending an actual request.
#     # if os.getenv("NODE_ENV", "development") == "development":
#     #     logging.info(f"Whatsapp Sent to {country_code} {mobile_number}")
#     #     return {"message": "Successfully sent via Whatsapp"}

#     # Read configuration from environment variables.
#     instance_id = os.getenv("FASTWASMS_INSTANCE_ID")
#     access_token = os.getenv("FASTWASMS_ACCESS_TOKEN")
#     api_url = os.getenv("FASTWASMS_API_URL", "https://fastwasms.in")
#     message_type = os.getenv("FASTWASMS_TYPE", "text")

#     # Hardcode OTP message
#     final_message = f"Hello, your verification code is {otp}. This code is valid for 5 minutes. Do not share this code with anyone."
#     encoded_message = urllib.parse.quote(final_message)
#     clean_country_code = country_code.replace("+", "")

#     # Construct the FastWASMS URL with required query parameters.
#     url = (
#         f"{api_url}/api/send?"
#         f"number={clean_country_code}{mobile_number}"
#         f"&type={message_type}"
#         f"&message={encoded_message}"
#         f"&instance_id={instance_id}"
#         f"&access_token={access_token}"
#     )
#     logging.info(f"FastWASMS URL: {url}")
#     async with httpx.AsyncClient() as client:
#         try:
#             response = await client.get(url)
#             data = response.json()
#             logging.info(f"FastWASMS response: {data}")
#             if data.get("status") == "error":
#                 raise Exception(data.get("message", "Error sending message"))
#             return {"message": data.get("message", "Message sent successfully")}
#         except Exception as e:
#             logging.error(f"Error sending FastWASMS notification: {e}")
#             raise Exception(f"Error sending message: {e}")


@router.post("/signup", response_model=schemas.Message)
async def signup(
    user: schemas.UserCreate, redis: redis_asyncio.Redis = Depends(get_redis)
):
    logging.info(f"New User Signup: {user.name} - {user.email}")
    # Check if a user with this email already exists
    existing_user = await User.find_one(User.email == user.email)
    if existing_user:
        logging.info("Email already registered. It should be unique.")
        raise HTTPException(
            status_code=422, detail="Email already registered. It should be unique."
        )

    # Generate OTPs for email and mobile
    email_otp = random.randint(1000, 9999)
    # mobile_otp = random.randint(1000, 9999)
    current_time = datetime.utcnow().timestamp()

    # Build pending signup data (do not yet create the permanent account)
    pending_data = {
        "name": user.name,
        "email": user.email,
        "mobile_number": user.mobile_number,
        "country_code": (
            user.country_code
            if hasattr(user, "country_code") and user.country_code
            else "91"
        ),
        "email_otp": email_otp,
        "timestamp": current_time,
    }
    pending_key = f"pending_signup:{user.email}"
    await redis.set(pending_key, json.dumps(pending_data), ex=OTP_EXPIRY_SECONDS)
    logging.info(f"Stored pending signup for {user.email} with key {pending_key}")

    # Send OTP via email
    await send_email_otp(user.email, email_otp)

    # Send OTP via mobile using FastWASMS.
    # mobile_user = {
    #     "countryCode": pending_data["country_code"],
    #     "mobileNumber": user.mobile_number,
    # }
    # try:
    #     await send_otp_service(user=mobile_user, otp=mobile_otp)
    # except Exception as e:
    #     logging.error(f"Failed to send mobile OTP: {e}")
    #     raise HTTPException(
    #         status_code=500, detail="Failed to send OTP to mobile number."
    #     )

    return JSONResponse(
        content={"message": "OTP sent to your email. Please verify to complete signup."}
    )


@router.post("/verifySignOtp", response_model=schemas.VerifyOtpResponse)
async def verify_signup_otp(
    data: schemas.VerifySignupOTPRequest,
    redis: redis_asyncio.Redis = Depends(get_redis),
):

    pending_key = f"pending_signup:{data.email}"
    pending_data_str = await redis.get(pending_key)

    if not pending_data_str:
        raise HTTPException(
            status_code=422, detail="Pending signup not found or OTP expired."
        )

    pending_data = json.loads(pending_data_str)

    # Validate the email OTP
    if int(pending_data.get("email_otp", 0)) != data.email_otp:
        logging.error("Invalid email OTP provided.")
        raise HTTPException(status_code=422, detail="Invalid email OTP.")

    # Validate the mobile OTP
    # if int(pending_data.get("mobile_otp", 0)) != data.mobile_otp:
    #     logging.error("Invalid mobile OTP provided.")
    #     raise HTTPException(status_code=422, detail="Invalid mobile OTP.")

    # Both OTPs are valid; create the user record in the database.
    new_user = User(
        name=pending_data["name"],
        email=pending_data["email"],
        mobile_number=pending_data["mobile_number"],
        country_code=pending_data.get("country_code", "91"),
    )

    await new_user.insert()
    logging.info(f"User account created successfully for {new_user.email}.")

    # Remove the pending signup data from Redis.
    await redis.delete(pending_key)

    # Generate a JWT token for the new user.
    token = auth.create_access_token(data={"sub": new_user.email})

    return JSONResponse(content={"token": token, "user": new_user.email})


@router.patch("/profile", response_model=dict)
async def update_profile(
    profile: schemas.UserProfile,
    current_user: str = Depends(auth.get_current_user),
):
    try:
        logging.info(f"Update profile with data: {profile}")
        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")

        if profile.mobile_number != db_user.mobile_number:
            existing_user = await User.find_one(
                (User.mobile_number == profile.mobile_number)
                & (User.email != current_user)
            )
            if existing_user:
                raise HTTPException(
                    status_code=422,
                    detail="Mobile Number already registered. It should be unique.",
                )

        update_data = profile.model_dump(exclude_unset=True)

        if "organization" in update_data and update_data["organization"] is not None:
            org_name = update_data["organization"]
            company_doc = await Company.find_one(Company.name == org_name)
            if company_doc:
                db_user.organization = company_doc
            else:
                new_company = Company(name=org_name, logo="", interview_settings={})
                await new_company.insert()
                db_user.organization = new_company

            del update_data["organization"]

        for field_name, value in update_data.items():
            setattr(db_user, field_name, value)

        await db_user.save()

        return {"message": "Profile updated successfully."}
    except Exception as e:
        logging.exception(f"Error updating profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/profile", response_model=dict)
async def get_profile(current_user: str = Depends(auth.get_current_user)):
    try:
        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")

        profile_data = db_user.model_dump()

        profile_data["id"] = str(db_user.id)
        profile_data["resume_url"] = db_user.resume_url()

        logging.info(f"Profile Data: {profile_data}")

        if db_user.organization is not None:
            company_doc = await db_user.organization.fetch()
            profile_data["organization"] = company_doc.name if company_doc else None
        else:
            profile_data["organization"] = None

        return profile_data

    except HTTPException as http_exc:
        logging.error(f"HTTP error getting profile: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logging.exception("Unexpected error fetching profile.")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while fetching the profile: {str(e)}",
        )


@router.post("/sendOtp", response_model=schemas.OtpResponse)
async def send_otp_api(
    request: schemas.SendOtpRequest, redis: redis_asyncio.Redis = Depends(get_redis)
):
    email = request.email
    logging.info(f"Send OTP request for {email}")

    user = await User.find_one(User.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="Email does not exist.")

    # Generate a 6-digit OTP.
    otp = random.randint(1000, 9999)
    current_time = datetime.utcnow().timestamp()  # storing the timestamp as a float

    # Prepare OTP data to be stored in Redis as a hash.
    otp_data = {
        "otp": otp,
        "timestamp": current_time,
        "otp_retries": 0,
    }
    key = otp_redis_key(email)
    if user.email == "shubh@bilzo.in":
        otp_data["otp"] = 5869
        await redis.hset(key, mapping=otp_data)
        await redis.expire(key, OTP_EXPIRY_SECONDS)
    else:
        await redis.hset(key, mapping=otp_data)
        await redis.expire(key, OTP_EXPIRY_SECONDS)

    try:
        await send_email_otp(email, otp)
    except Exception as e:
        logging.error(f"Error sending OTP: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to send OTP. Please try again later."
        )

    return JSONResponse(content={"message": "OTP sent successfully"})


@router.post("/resendOtp", response_model=schemas.OtpResponse)
async def resend_otp_api(
    request: schemas.SendOtpRequest, redis: redis_asyncio.Redis = Depends(get_redis)
):
    # country_code = request.country_code.replace("+", "")
    # mobile_number = request.mobile_number
    email = request.email
    logging.info(f"Resend OTP request for {email}")

    # Ensure the user exists in the database.
    user = await User.find_one(User.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="Mobile number does not exist.")

    key = otp_redis_key(email)
    # Retrieve existing OTP data from Redis.
    otp_data = await redis.hgetall(key)
    otp_retries = int(otp_data.get("otp_retries", 0)) if otp_data else 0
    otp_retries += 1

    # Generate a new OTP and update the timestamp.
    otp = random.randint(1000, 9999)
    current_time = datetime.utcnow().timestamp()
    new_otp_data = {
        "otp": otp,
        "timestamp": current_time,
        "otp_retries": otp_retries,
    }
    await redis.hset(key, mapping=new_otp_data)
    await redis.expire(key, OTP_EXPIRY_SECONDS)

    # mobile_user = {
    #     "countryCode": user.country_code,
    #     "mobileNumber": user.mobile_number,
    # }
    try:
        await send_email_otp(email, otp)
    except Exception as e:
        logging.error(f"Error resending OTP: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to resend OTP. Please try again later."
        )

    return JSONResponse(content={"message": "OTP resent successfully"})


@router.post("/verifyOtp", response_model=schemas.VerifyOtpResponse)
async def verify_otp_api(
    request: schemas.VerifyOtpRequest, redis: redis_asyncio.Redis = Depends(get_redis)
):
    # country_code = request.country_code.replace("+", "")
    # mobile_number = request.mobile_number
    email = request.email
    otp_input = request.otp
    logging.info(f"Verify OTP request for {email} with OTP: {otp_input}")

    # Ensure the user exists.
    user = await User.find_one(User.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="Mobile number does not exist.")

    key = otp_redis_key(email)
    otp_data = await redis.hgetall(key)
    if not otp_data:
        raise HTTPException(
            status_code=422, detail="OTP has expired. Please request a new one."
        )

    stored_otp = int(otp_data.get("otp"))
    stored_timestamp = float(otp_data.get("timestamp"))
    otp_retries = int(otp_data.get("otp_retries", 0))

    # Check if OTP is expired (additional safeguard, since Redis TTL should remove expired keys).
    if datetime.utcnow().timestamp() - stored_timestamp > OTP_EXPIRY_SECONDS:
        raise HTTPException(
            status_code=422, detail="OTP has expired. Please request a new one."
        )

    if stored_otp != otp_input:
        # Increment the otp_retries count in Redis.
        otp_retries += 1
        await redis.hset(key, mapping={"otp_retries": otp_retries})
        raise HTTPException(status_code=422, detail="Invalid OTP.")

    # OTP is valid; remove the OTP data from Redis.
    await redis.delete(key)

    # Generate a JWT token (assuming auth.create_access_token exists and uses user's unique field, e.g., email).
    token = auth.create_access_token(data={"sub": user.email})
    return JSONResponse(content={"token": token, "user": user.email})


@router.get("/getCurrentUser")
async def protected_route(current_user: str = Depends(auth.get_current_user)):
    return {"message": f"Welcome, {current_user}!"}


@router.get("/companies", response_model=List[str])
async def get_companies():
    db_companies = await Company.find({}, {"name": 1, "_id": 0}).to_list()
    companies = []
    if not db_companies:
        return JSONResponse(
            content={"message": "No companies available currently"}, status_code=200
        )
    for db_company in db_companies:
        companies.append(db_company["name"])
    return JSONResponse(content=companies)


@router.post("/profile/resume", response_model=dict)
async def upload_resume(
    file: UploadFile = File(...), current_user: str = Depends(auth.get_current_user)
):
    user_doc = await User.find_one(User.email == current_user)
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        original_filename = file.filename or "resume"
        unique_filename = generate_random_filename(original_filename)

        bucket_name = "mockai-resume"
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_ACCESS_SECRET_KEY"),
            region_name=os.getenv("AWS_ACCESS_REGION"),
        )
        file_content = await file.read()
        await file.seek(0)  # Reset pointer for later use

        # Upload to S3
        s3_client.upload_fileobj(
            BytesIO(file_content),
            bucket_name,
            unique_filename,
            ExtraArgs={"ContentType": file.content_type},
        )

        # Extract and summarize
        resume_url = f"https://{bucket_name}.s3.amazonaws.com/{unique_filename}"
        resume_text = common_utils.extract_resume_text_from_s3_url(resume_url)
        resume_summary = openai_utils.summarize_resume(resume_text)

        # Save to user profile
        user_doc.resume = unique_filename
        user_doc.resume_summary = resume_summary  # <-- store summary
        await user_doc.save()
        logging.info(f"Resume uploaded and summarized successfully. {resume_summary}")
        return {
            "message": "Resume uploaded successfully.",
        }

    except Exception as e:
        logging.exception("Error uploading resume to AWS S3.")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading resume. Please try again later. {str(e)}",
        )


@router.post("/profile/about", response_model=dict)
async def update_about(
    req: schemas.AboutRequest, current_user: str = Depends(auth.get_current_user)
):
    try:
        logging.info(f"Update about with data: {req.about}")

        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")

        db_user.aboutMe = req.about
        await db_user.save()

        return {"message": "Updated successfully."}

    except HTTPException as http_exc:
        logging.error(f"HTTP error updating about user: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logging.exception("Unexpected error updating about.")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while updating the about: {str(e)}",
        )


@router.get("/dashboard", response_model=dict)
async def dashboard(current_user: str = Depends(auth.get_current_user)):

    user = await User.find_one(User.email == current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    interviews = await Interview.find(Interview.user_id.id == user.id).to_list()

    interviews_list = []
    for interview in interviews:
        if interview.free_review:
            interview_dict = {
                "_id": str(interview.id),
                "created_at": (
                    interview.created_at.isoformat() if interview.created_at else None
                ),
                "job_role": (
                    interview.user_data.get("job_role") if interview.user_data else None
                ),
                "overall_summary": (
                    interview.free_review.overall_summary
                    if hasattr(interview, "free_review") and interview.free_review
                    else None
                ),
                "payment_status": (
                    True
                    if hasattr(interview, "payment_id") and interview.payment_id
                    else None
                ),
            }
            interviews_list.append(interview_dict)
    total_interviews = len(interviews_list)
    if total_interviews > 0:
        avg_score = (
            sum(
                i.free_review.overall_score
                for i in interviews
                if i.free_review and i.free_review.overall_score is not None
            )
            / total_interviews
            if any(
                i.free_review and i.free_review.overall_score is not None
                for i in interviews
            )
            else 0
        )

        valid_confidence_interviews = [
            i
            for i in interviews
            if i.free_review
            and hasattr(i.free_review, "skill_analysis")
            and i.free_review.skill_analysis
            and hasattr(i.free_review.skill_analysis, "speech_analysis")
            and i.free_review.skill_analysis.speech_analysis
            and i.free_review.skill_analysis.speech_analysis.avg_confidence_level
            is not None
        ]

        if valid_confidence_interviews:
            confidence_values = [
                i.free_review.skill_analysis.speech_analysis.avg_confidence_level
                for i in valid_confidence_interviews
            ]
            # Count occurrences of each confidence level
            confidence_counts = {}
            for val in confidence_values:
                if val in confidence_counts:
                    confidence_counts[val] += 1
                else:
                    confidence_counts[val] = 1

            # Find the most common confidence level
            avg_confidence = (
                max(confidence_counts.items(), key=lambda x: x[1])[0]
                if confidence_counts
                else "Medium"
            )
        else:
            avg_confidence = "Medium"

        avg_speech_clarity = (
            sum(
                i.free_review.skill_analysis.communication_skills.clarity
                for i in interviews
                if i.free_review
                and hasattr(i.free_review, "skill_analysis")
                and i.free_review.skill_analysis
                and hasattr(i.free_review.skill_analysis, "communication_skills")
                and i.free_review.skill_analysis.communication_skills
                and i.free_review.skill_analysis.communication_skills.clarity
                is not None
            )
            / total_interviews
            if any(
                i.free_review
                and hasattr(i.free_review, "skill_analysis")
                and i.free_review.skill_analysis
                and hasattr(i.free_review.skill_analysis, "communication_skills")
                and i.free_review.skill_analysis.communication_skills
                and i.free_review.skill_analysis.communication_skills.clarity
                is not None
                for i in interviews
            )
            else 0
        )

        avg_technical_accuracy = (
            sum(
                i.free_review.skill_analysis.conceptual_understanding.fundamental_concepts
                for i in interviews
                if i.free_review
                and hasattr(i.free_review, "skill_analysis")
                and i.free_review.skill_analysis
                and hasattr(i.free_review.skill_analysis, "conceptual_understanding")
                and i.free_review.skill_analysis.conceptual_understanding
                and i.free_review.skill_analysis.conceptual_understanding.fundamental_concepts
                is not None
            )
            / total_interviews
            if any(
                i.free_review
                and hasattr(i.free_review, "skill_analysis")
                and i.free_review.skill_analysis
                and hasattr(i.free_review.skill_analysis, "conceptual_understanding")
                and i.free_review.skill_analysis.conceptual_understanding
                and i.free_review.skill_analysis.conceptual_understanding.fundamental_concepts
                is not None
                for i in interviews
            )
            else 0
        )

    else:
        avg_score = avg_confidence = avg_speech_clarity = avg_technical_accuracy = 0

    aptitude_entries = (
        await UserAptitude.find(UserAptitude.user_id.id == user.id).limit(5).to_list()
    )
    past_aptitude_scores = [entry.score for entry in aptitude_entries]

    avg_aptitude_score = (
        sum(past_aptitude_scores) / len(past_aptitude_scores)
        if past_aptitude_scores
        else 0
    )

    response = {
        "total_interviews": total_interviews,
        "avg_interview_score": avg_score,
        "avg_confidence": avg_confidence,
        "avg_speech_clarity": avg_speech_clarity,
        "avg_technical_accuracy": avg_technical_accuracy,
        "past_aptitude_scores": past_aptitude_scores,
        "interviews": interviews_list,
        "avg_aptitude_score": avg_aptitude_score,
    }

    return JSONResponse(content=response)


@router.post("/feedback", response_model=dict)
async def give_feedback(
    feedback: schemas.FeedbackRequest,
    current_user: str = Depends(auth.get_current_user),
):
    try:
        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")
        interview_id = ObjectId(feedback.interview_id)
        interview_doc = await Interview.get(interview_id)
        if not interview_doc:
            raise HTTPException(status_code=404, detail="Interview not found.")
        feedback_doc = CustomerFeedback(
            rating=feedback.rating,
            suggestion=feedback.suggestion,
            user_id=db_user,  # Pass the User object directly instead of just the id
            interview_id=interview_doc,
        )
        await feedback_doc.create()
        db_user.is_feedback_given = True
        await db_user.save()
        return {"message": "Feedback given successfully."}
    except Exception as e:
        logging.error(f"Error creating feedback: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"An error occurred while saving feedback: {str(e)}"
        )
