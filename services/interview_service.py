from fastapi import Depends, HTTPException, APIRouter, Query, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from models.interview import (
    Interview,
    QuestionResponse,
    SpeechAnalysis,
    CustomerFeedback,
    FreeReview,
    PaidReview,
)
from models.payment import Payment
from models.users import User
from models.user_aptitude import UserAptitude
import schemas, auth
import openai_utils
import json
import logging
from datetime import datetime
from bson import ObjectId
import openai
import io
import os
import razorpay
from google.cloud import texttospeech, storage
import librosa
from dotenv import load_dotenv
import common_utils

load_dotenv()

router = APIRouter()
client = texttospeech.TextToSpeechClient()
storage_client = storage.Client()
BUCKET_NAME = "mockai-resume"
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

openai.api_key = os.getenv("OPENAI_API_KEY")


@router.post("/create_interview", response_model=schemas.InterviewCreateOut)
async def create_interview(
    current_user: str = Depends(auth.get_current_user),
    aptitude_id: str = Query(None),
):
    # 1) Fetch user doc via Beanie
    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    linked_aptitude = None
    if aptitude_id:
        try:
            apt_id = ObjectId(aptitude_id)
            linked_aptitude = await UserAptitude.find_one(UserAptitude.id == apt_id)
        except:
            linked_aptitude = None

    company_doc = None
    if db_user.organization:
        company_doc = await db_user.organization.fetch()

    company_logo = (
        company_doc.logo if company_doc and company_doc.logo else "MockAI Tech"
    )

    interview_doc = Interview(
        user_id=db_user,
        company_id=company_doc if company_doc else None,
        user_aptitude_id=linked_aptitude if linked_aptitude else None,
        question_responses=[],
        user_data={
            "job_role": db_user.job_role,
            "years_of_experience": db_user.years_of_experience,
            "field": db_user.field,
        },
    )

    await interview_doc.insert()

    return JSONResponse(
        content={
            "interview_id": str(interview_doc.id),
            "company_logo": company_logo,
        }
    )


@router.post("/generate_questions", response_model=schemas.InterviewQuestionsOut)
async def generate_questions(
    interview_id: str = Query(...),
    current_user: str = Depends(auth.get_current_user),
):
    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        interview_obj_id = ObjectId(interview_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid interview_id") from e

    interview_doc = await Interview.get(interview_obj_id)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")
    if str(interview_doc.user_id.ref.id) != str(db_user.id):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this interview."
        )

    # Return existing questions if already generated
    if interview_doc.question_responses and len(interview_doc.question_responses) > 0:
        return JSONResponse(
            content={
                "questions": [q.dict() for q in interview_doc.question_responses],
                "interview_id": str(interview_doc.id),
                "completion_percentage": interview_doc.completion_percentage,
            }
        )

    if db_user.resume_summary and len(db_user.resume_summary) > 0:
        logging.info("Using cached resume summary")
        resume_summary = db_user.resume_summary
    else:
        logging.info("Extracting resume summary from S3")
        bucket_name = "mockai-resume"
        resume_url = f"https://{bucket_name}.s3.amazonaws.com/{db_user.resume}"
        logging.info(f"Resume URL: {resume_url}")
        resume_text = common_utils.extract_resume_text_from_s3_url(resume_url)
        resume_summary = openai_utils.summarize_resume(resume_text)
        db_user.resume_summary = resume_summary
        await db_user.save()
    company_doc = await db_user.organization.fetch()
    previous_interview = (
        await Interview.find(
            {"user_id.$id": ObjectId(db_user.id)},
            {"_id": {"$ne": ObjectId(interview_doc.id)}},
            {"question_responses": {"$ne": None}},
        )
        .sort("-created_at")
        .first_or_none()
    )
    previous_questions = []
    if previous_interview:
        for q in previous_interview.question_responses:
            if q.question:
                previous_questions.append(q.question)

    logging.info(f"Found {len(previous_questions)} previous questions")
    try:
        agent_response = openai_utils.generate_initial_question(
            job_role=db_user.job_role,
            company=company_doc.name,
            resume_summary=resume_summary,
            field=db_user.field,
            years_of_experience=db_user.years_of_experience,
            previous_questions=previous_questions,
        )

        parsed = json.loads(agent_response.get("text", agent_response))

    except Exception as e:
        logging.error("Error generating questions from AI agent: %s", e)
        raise HTTPException(
            status_code=500, detail="Error generating interview questions."
        )

    question_list = parsed.get("questions", [])
    question_responses = [QuestionResponse(question=q) for q in question_list]

    interview_doc.question_responses = question_responses
    await interview_doc.save()

    return JSONResponse(
        content={
            "questions": [q.dict() for q in question_responses],
            "interview_id": str(interview_doc.id),
            "completion_percentage": 0,
        }
    )


@router.post("/submit_interview")
async def interview_convo(
    interview_id: str = Query(...),
    current_user: str = Depends(auth.get_current_user),
):
    # get thread_id and assistant_id from db
    db_user = await User.find_one(User.email == current_user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        interview_obj_id = ObjectId(interview_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid interview_id") from e

    # Retrieve the interview document
    interview_doc = await Interview.get(interview_obj_id)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if interview_doc.free_review:
        return JSONResponse(
            content={
                "message": "Interview already submitted.",
                "review": interview_doc.free_review.dict(),
                "user_data": interview_doc.user_data,
                "completion_percentage": interview_doc.completion_percentage,
            }
        )
    responses_list = []
    for qa in interview_doc.question_responses:
        combined = {"question_id": qa.question_id, "question": qa.question}

        if qa.speech_analysis is not None:
            analysis_dict = qa.speech_analysis.model_dump()
            combined = {**combined, **analysis_dict}

        responses_list.append(combined)

    answered_questions = sum(
        1 for qa in interview_doc.question_responses if qa.speech_analysis is not None
    )

    # Check if there are at least 4 answered questions
    if answered_questions < 4:
        return JSONResponse(
            status_code=400,
            content={
                "message": "Not enough responses. At least 4 answers are required to submit the interview.",
                "answered_count": answered_questions,
                "total_questions": len(interview_doc.question_responses),
            },
        )

    responses_json = json.dumps(responses_list)
    try:
        free_feedback_raw = openai_utils.generate_feedback(
            responses_json,
            len(interview_doc.question_responses),
            answered_questions,
            answered_questions * 10,
        )

        # Handle the case when the response could be a string or dict with nested structure
        if isinstance(free_feedback_raw, str):
            free_feedback = json.loads(free_feedback_raw)
        elif isinstance(free_feedback_raw, dict):
            if "text" in free_feedback_raw:
                # Handle when the response is in the "text" field as a JSON string
                try:
                    free_feedback = json.loads(free_feedback_raw["text"])
                except:
                    free_feedback = free_feedback_raw["text"]
            else:
                free_feedback = free_feedback_raw
        else:
            raise ValueError(f"Unexpected response type: {type(free_feedback_raw)}")

    except Exception as e:
        logging.error("Error generating free feedback from AI agent: %s", e)
        logging.error(f"Raw response: {free_feedback_raw}")
        raise HTTPException(status_code=500, detail="Error generating free feedback.")

    interview_doc.free_review = FreeReview(**free_feedback)
    await interview_doc.save()
    user_data = interview_doc.user_data.copy() if interview_doc.user_data else {}

    user_data["date"] = (
        interview_doc.created_at.isoformat() if interview_doc.created_at else None
    )
    return JSONResponse(
        content={
            "message": "Interview submitted successfully.",
            "review": free_feedback,
            "user_data": user_data,
            "completion_percentage": interview_doc.completion_percentage,
        }
    )


@router.get("/paid")
async def interview_feedback(
    interview_id: str = Query(...), current_user: str = Depends(auth.get_current_user)
):
    db_user = await User.find_one(User.email == current_user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        interview_obj_id = ObjectId(interview_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid interview_id") from e

    interview_doc = await Interview.get(interview_obj_id)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if not interview_doc.payment_id:
        raise HTTPException(
            status_code=403,
            detail="This interview requires payment for detailed feedback.",
        )
    user_data = interview_doc.user_data.copy() if interview_doc.user_data else {}

    user_data["date"] = (
        interview_doc.created_at.isoformat() if interview_doc.created_at else None
    )
    if interview_doc.paid_review:
        paid_feedback = interview_doc.paid_review.dict()

        speech_analysis_map = {}
        for qa in interview_doc.question_responses or []:
            if qa.speech_analysis:
                speech_analysis_map[qa.question_id] = {
                    "fluency_score": qa.speech_analysis.fluency_score,
                    "confidence_score": qa.speech_analysis.confidence_score,
                    "clarity_score": qa.speech_analysis.clarity_score,
                    "filler_words": qa.speech_analysis.filler_words,
                    "time_seconds": qa.speech_analysis.time_seconds,
                    "words_per_minute": qa.speech_analysis.words_per_minute,
                    "answer": qa.speech_analysis.transcript,
                    "answer_relevance_score": qa.speech_analysis.answer_relevance_score,
                }

        # Modify this section to handle questions without speech analysis
        if "question_analysis" in paid_feedback:
            for analysis in paid_feedback["question_analysis"]:
                q_id = analysis.get("question_id")
                # Add speech analysis if available, otherwise keep existing analysis
                if q_id in speech_analysis_map:
                    analysis.update(speech_analysis_map[q_id])
                elif not any(
                    key in analysis
                    for key in [
                        "fluency_score",
                        "confidence_score",
                        "clarity_score",
                        "filler_words",
                        "time_seconds",
                        "words_per_minute",
                        "answer",
                        "answer_relevance_score",
                    ]
                ):
                    # If no speech analysis exists, add placeholder or keep existing data
                    analysis.update(
                        {
                            "fluency_score": None,
                            "confidence_score": None,
                            "clarity_score": None,
                            "filler_words": [],
                            "time_seconds": None,
                            "answer": None,
                            "words_per_minute": None,
                            "answer_relevance_score": None,
                        }
                    )

        return JSONResponse(
            content={
                "paid_review": paid_feedback,
                "review": interview_doc.free_review.dict(),
                "user_data": user_data,
                "completion_percentage": interview_doc.completion_percentage,
            }
        )

    question_answer_list = []
    for qa in interview_doc.question_responses or []:
        question_answer_list.append(
            {
                "question_id": qa.question_id,
                "question": qa.question,
                "answer": (
                    qa.speech_analysis.transcript
                    if (qa.speech_analysis and qa.speech_analysis.transcript)
                    else None
                ),
            }
        )

    responses_json = json.dumps(question_answer_list)

    try:
        raw_paid_feedback = openai_utils.generate_feedback_paid(
            qaa=responses_json, years_of_experience=db_user.years_of_experience
        )

        logging.info("Raw paid feedback LLM response: %s", raw_paid_feedback)
        formatted_paid_feedback = common_utils.extract_json_from_llm_text(
            raw_paid_feedback
        )
        if isinstance(formatted_paid_feedback, dict):
            paid_feedback = formatted_paid_feedback
        elif isinstance(formatted_paid_feedback, str):
            paid_feedback = json.loads(formatted_paid_feedback)
        else:
            paid_feedback = formatted_paid_feedback

        speech_analysis_map = {}
        for qa in interview_doc.question_responses or []:
            if qa.speech_analysis:
                speech_analysis_map[qa.question_id] = {
                    "fluency_score": qa.speech_analysis.fluency_score,
                    "confidence_score": qa.speech_analysis.confidence_score,
                    "clarity_score": qa.speech_analysis.clarity_score,
                    "filler_words": qa.speech_analysis.filler_words,
                    "time_seconds": qa.speech_analysis.time_seconds,
                    "words_per_minute": qa.speech_analysis.words_per_minute,
                    "answer": qa.speech_analysis.transcript,
                    "answer_relevance_score": qa.speech_analysis.answer_relevance_score,
                }

        # Modify this section to handle questions without speech analysis
        if "question_analysis" in paid_feedback:
            for analysis in paid_feedback["question_analysis"]:
                q_id = analysis.get("question_id")
                # Add speech analysis if available, otherwise keep existing analysis
                if q_id in speech_analysis_map:
                    analysis.update(speech_analysis_map[q_id])
                elif not any(
                    key in analysis
                    for key in [
                        "fluency_score",
                        "confidence_score",
                        "clarity_score",
                        "filler_words",
                        "time_seconds",
                        "words_per_minute",
                        "answer",
                        "answer_relevance_score",
                    ]
                ):
                    # If no speech analysis exists, add placeholder or keep existing data
                    analysis.update(
                        {
                            "fluency_score": None,
                            "confidence_score": None,
                            "clarity_score": None,
                            "filler_words": [],
                            "time_seconds": None,
                            "words_per_minute": None,
                            "answer": None,
                            "answer_relevance_score": None,
                        }
                    )

    except Exception as e:
        logging.error("Error generating paid feedback: %s", e)
        raise HTTPException(status_code=500, detail="Error generating paid feedback.")

    interview_doc.paid_review = PaidReview(**paid_feedback)
    await interview_doc.save()

    if not interview_doc.free_review:
        logging.info("Unable to find free review, generating free review!!!!!")
        responses_list = []
        for qa in interview_doc.question_responses:
            combined = {"question_id": qa.question_id, "question": qa.question}

            if qa.speech_analysis is not None:
                analysis_dict = qa.speech_analysis.model_dump()
                combined = {**combined, **analysis_dict}

            responses_list.append(combined)

        answered_questions = sum(
            1
            for qa in interview_doc.question_responses
            if qa.speech_analysis is not None
        )
        for qa in interview_doc.question_responses:
            combined = {"question_id": qa.question_id, "question": qa.question}
            if qa.speech_analysis is not None:
                analysis_dict = qa.speech_analysis.model_dump()
                combined = {**combined, **analysis_dict}
            responses_list.append(combined)

        responses_json = json.dumps(responses_list)
        free_feedback_raw = openai_utils.generate_feedback(
            responses_json,
            len(interview_doc.question_responses),
            answered_questions,
            answered_questions * 10,
        )
        if isinstance(free_feedback_raw, str):
            free_feedback = json.loads(free_feedback_raw)
        elif isinstance(free_feedback_raw, dict):
            if "text" in free_feedback_raw:
                try:
                    free_feedback = json.loads(free_feedback_raw["text"])
                except:
                    free_feedback = free_feedback_raw["text"]
            else:
                free_feedback = free_feedback_raw
        else:
            raise ValueError(f"Unexpected response type: {type(free_feedback_raw)}")

        interview_doc.free_review = FreeReview(**free_feedback)
        await interview_doc.save()

    return JSONResponse(
        content={
            "paid_review": paid_feedback,
            "review": interview_doc.free_review.dict(),
            "user_data": user_data,
            "completion_percentage": interview_doc.completion_percentage,
        }
    )


@router.post("/transcribe")
async def transcribe_audio(
    question_id: str = Query(...),
    interview_id: str = Query(...),
    completion_percentage: str = Query(...),
    audio: UploadFile = File(...),
    current_user: str = Depends(auth.get_current_user),
):
    logging.info(
        f"Transcribe request received - interview_id: {interview_id}, question_id: {question_id}"
    )
    try:
        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")

        try:
            interview_obj_id = ObjectId(interview_id)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid interview_id: {str(e)}"
            )

        interview_doc = await Interview.get(interview_obj_id)
        if not interview_doc:
            raise HTTPException(status_code=404, detail="Interview not found.")

        # Read audio
        audio_bytes = await audio.read()
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file received")

        audio_file = io.BytesIO(audio_bytes)

        # Extract audio duration
        try:
            audio_data, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=None)
            duration_seconds = librosa.get_duration(y=audio_data, sr=sample_rate)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not decode audio. Ensure valid format. Error: {str(e)}",
            )

        # Transcribe audio
        audio_file.seek(0)
        try:
            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {openai.api_key}"}
            data = {"model": "whisper-1"}
            files = {"file": ("recording.wav", audio_file, "audio/wav")}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url, headers=headers, data=data, files=files
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"OpenAI API error: {response.text}",
                )

            response_json = response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="OpenAI API request timed out")
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail=f"OpenAI API request failed: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"OpenAI Whisper error: {str(e)}"
            )

        transcript_text = response_json.get("text", "").strip()
        if not transcript_text:
            logging.warning("Empty transcript returned from OpenAI Whisper")

        # Find question text
        question_text = None
        if interview_doc.question_responses:
            for qr in interview_doc.question_responses:
                if qr.question_id == question_id:
                    question_text = qr.question
                    break

        if not question_text:
            raise HTTPException(
                status_code=404, detail="question_id not found in interview"
            )
        speech_metrics = openai_utils.analyze_audio(
            question_text=question_text,
            transcript_text=transcript_text,
            duration_seconds=duration_seconds,
        )

        # Parse the JSON response from speech_metrics
        try:
            metrics_dict = json.loads(speech_metrics["text"])
            logging.info("Parsed metrics dict: %s", metrics_dict)
        except (json.JSONDecodeError, KeyError) as e:
            logging.error("Error parsing speech metrics: %s", e)
            metrics_dict = {}

        # Update question response
        for qr in interview_doc.question_responses:
            if qr.question_id == question_id:
                qr.speech_analysis = SpeechAnalysis(
                    transcript=transcript_text,
                    fluency_score=metrics_dict.get("fluency_score", 0.0),
                    confidence_score=metrics_dict.get("confidence_score", 0.0),
                    clarity_score=metrics_dict.get("clarity_score", 0.0),
                    words_per_minute=metrics_dict.get("words_per_minute", 0.0),
                    filler_words=metrics_dict.get("filler_words_used", []),
                    time_seconds=duration_seconds,
                    answer_relevance_score=metrics_dict.get(
                        "answer_relevance_score", 0.0
                    ),
                )
                break

        interview_doc.completion_percentage = int(completion_percentage)
        await interview_doc.save()

        return JSONResponse(
            content={
                "message": f"Transcription and analysis complete for question {question_id}"
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logging.error(f"Unhandled exception in transcribe endpoint: {str(e)}")
        import traceback

        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/synthesize_speech")
async def synthesize_speech(request: schemas.TextToSpeechRequest):
    try:
        # Set up the synthesis input
        text = request.text
        print(text)
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Configure the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-IN",  # Change language as needed
            name="en-IN-Wavenet-D",  # Use a high-quality voice
        )

        # Configure the audio output
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,  # Use MP3 for better compatibility
        )

        # Perform the text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        # Wrap the audio content in a BytesIO stream and return as a StreamingResponse
        return StreamingResponse(
            io.BytesIO(response.audio_content), media_type="audio/mpeg"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/customer_feedback")
async def create_customer_feedback(
    feedback_in: CustomerFeedback,
    interview_id: str = Query(...),
    current_user: str = Depends(auth.get_current_user),
):
    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        interview_oid = ObjectId(interview_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid interview_id.")

    interview_doc = await Interview.get(interview_oid)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    feedback_doc = CustomerFeedback(
        rating=feedback_in.rating,
        suggestion=feedback_in.suggestion,
        user_id=db_user.id,
    )

    interview_doc.customer_feedback = feedback_doc
    await interview_doc.save()

    return JSONResponse({"message": "Customer feedback added successfully"})


# Need to add an api for razor pay payment gateway


@router.get("/check_review")
async def check_review_availability(
    interview_id: str = Query(...), current_user: str = Depends(auth.get_current_user)
):

    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        interview_obj_id = ObjectId(interview_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid interview_id")

    interview_doc = await Interview.get(interview_obj_id)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if interview_doc.user_id != db_user.id:
        raise HTTPException(
            status_code=403, detail="Cannot view another user's interview."
        )

    existing_payment = await Payment.find_one(
        Payment.user_id == db_user.id, Payment.reviews_bought > 0
    )

    if existing_payment:
        return {
            "review_available": True,
            "message": "You have an existing review credit you can use.",
        }
    else:
        return {
            "review_available": False,
            "message": "No leftover reviews. Proceed to payment.",
        }


@router.post("/create_order")
async def proceed_payment(
    interview_id: str = Query(...), current_user: str = Depends(auth.get_current_user)
):
    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        interview_obj_id = ObjectId(interview_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid interview_id")

    interview_doc = await Interview.get(interview_obj_id)
    if not interview_doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if interview_doc.user_id is None:
        raise HTTPException(status_code=404, detail="Interview has no associated user.")

    interview_user = await interview_doc.user_id.fetch()
    if interview_user.id != db_user.id:
        raise HTTPException(
            status_code=403, detail="Cannot pay for another user's interview."
        )

    order_amount_paise = 2900
    order_data = {
        "amount": order_amount_paise,
        "currency": "INR",
        "payment_capture": 1,
        # "notes": {"user_id": str(db_user.id), "interview_id": str(interview_doc.id)},
        "notes": {"user_id": str(db_user.id)},
    }
    try:
        razorpay_order = razorpay_client.order.create(data=order_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Razorpay error: {str(e)}")

    # Return order details
    return {
        "order_id": razorpay_order["id"],
        "amount": razorpay_order["amount"],
        "currency": razorpay_order["currency"],
        "key": os.getenv("RAZORPAY_KEY_ID"),
        "notes": razorpay_order["notes"],
    }


@router.post("/verify_order")
async def verify_payment(
    payload: schemas.VerifyPaymentInput,
    interview_id: str = Query(...),
    current_user: str = Depends(auth.get_current_user),
):
    data = {
        "razorpay_order_id": payload.order_id,
        "razorpay_payment_id": payload.payment_id,
        "razorpay_signature": payload.signature,
    }
    try:
        razorpay_client.utility.verify_payment_signature(data)
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Razorpay signature")

    # 2) Identify the user making this call
    db_user = await User.find_one(User.email == current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3) Query Razorpay for order details (to retrieve the interview_id from 'notes')
    try:
        rzp_order = razorpay_client.order.fetch(payload.order_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching order: {str(e)}")

    new_payment = Payment(
        transaction_id=payload.payment_id,
        amount=payload.reviews_bought * 29.0,  # e.g. 1 review = 100 INR
        payment_date=datetime.utcnow().date(),
        user_id=db_user,
        reviews_bought=payload.reviews_bought,
    )
    await new_payment.insert()

    interview_doc = None
    if interview_id:
        try:
            interview_obj_id = ObjectId(interview_id)
            interview_doc = await Interview.get(interview_obj_id)
        except:
            interview_doc = None

    if interview_doc:
        # Fetch user from interview and verify ownership
        interview_user = await interview_doc.user_id.fetch()
        if interview_user.id != db_user.id:
            raise HTTPException(
                status_code=403, detail="Cannot modify another user's interview."
            )

        if new_payment.reviews_bought <= 0:
            raise HTTPException(status_code=400, detail="No reviews left to deduct.")
        new_payment.reviews_bought -= 1
        await new_payment.save()

        interview_doc.payment_id = new_payment
        await interview_doc.save()

    return {
        "message": "Payment verified and 1 review deducted from your purchase.",
        "payment_id": str(new_payment.id),
        "reviews_left": new_payment.reviews_bought,
    }
