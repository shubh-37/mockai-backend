from fastapi import Depends, HTTPException, APIRouter, Query, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from models.company import Company
import tempfile
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

load_dotenv()

router = APIRouter()
client = texttospeech.TextToSpeechClient()
storage_client = storage.Client()
BUCKET_NAME = "mockai-resume"
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

openai.api_key = os.getenv("OPENAI_API_KEY")


def analyze_speech(transcript_text, duration_seconds):
    """Analyze speech transcript and return metrics."""
    if not transcript_text or duration_seconds <= 0:
        return {
            "fluency_score": 0.0,
            "confidence_score": 0.0,
            "clarity_score": 0.0,
            "words_per_minute": 0.0,
            "filler_word_counts": {},
            "total_filler_count": 0,
            "filler_frequency": 0.0,
        }

    # List of common filler words/phrases
    filler_list = [
        "um",
        "uh",
        "like",
        "so",
        "you know",
        "er",
        "ah",
        "hmm",
        "well",
        "actually",
    ]

    # Clean transcript and split into words
    words = transcript_text.lower().split()
    word_count = len(words)

    # Calculate words per minute
    words_per_minute = (word_count / duration_seconds) * 60

    # Count each filler word (full word matches only)
    filler_word_counts = {}
    total_filler_count = 0

    # Check complete words only (not substrings)
    for word in words:
        # Clean the word of punctuation
        clean_word = word.strip(".,!?;:'\"()[]{}").lower()
        if clean_word in filler_list:
            filler_word_counts[clean_word] = filler_word_counts.get(clean_word, 0) + 1
            total_filler_count += 1

    # Also check for multi-word fillers like "you know"
    transcript_lower = transcript_text.lower()
    for filler in filler_list:
        if " " in filler:  # it's a multi-word filler
            count = transcript_lower.count(filler)
            if count > 0:
                filler_word_counts[filler] = count
                total_filler_count += count

    # Calculate filler frequency (fillers per 100 words)
    filler_frequency = (total_filler_count / word_count * 100) if word_count > 0 else 0

    # Calculate speech metrics
    # Fluency: penalize based on filler word frequency (how many fillers per 100 words)
    # - 0% fillers = 100 score
    # - 10% fillers = 50 score
    # - 20%+ fillers = 0 score
    fluency_score = max(0.0, 100.0 - (filler_frequency * 5.0))

    # Confidence: Based on speaking rate and filler usage
    # Speaking rate component (40% of score)
    # Optimal range is ~120-160 WPM, with penalties for too slow or too fast
    rate_score = 0
    if words_per_minute < 80:
        rate_score = words_per_minute / 2  # Slower speech gets lower score
    elif words_per_minute <= 160:
        rate_score = 40  # Optimal range gets full points
    else:
        rate_score = max(0, 40 - (words_per_minute - 160) / 10)  # Penalty for too fast

    # Filler component (60% of score)
    filler_score = max(0, 60 - (filler_frequency * 3))

    # Combined confidence score
    confidence_score = rate_score + filler_score

    # Clarity: Penalize for filler words, but less harshly than fluency
    clarity_score = max(0.0, 100.0 - (filler_frequency * 2.5))

    return {
        "fluency_score": round(fluency_score, 1),
        "confidence_score": round(confidence_score, 1),
        "clarity_score": round(clarity_score, 1),
        "words_per_minute": round(words_per_minute, 1),
        "filler_word_counts": filler_word_counts,
        "total_filler_count": total_filler_count,
        "filler_frequency": round(filler_frequency, 1),
    }


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
    logging.info(str(interview_doc.user_id.ref.id))
    logging.info(str(db_user.id))
    if str(interview_doc.user_id.ref.id) != str(db_user.id):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this interview."
        )

    # Check if questions already exist
    if interview_doc.question_responses and len(interview_doc.question_responses) > 0:

        return JSONResponse(
            content={
                "questions": [q.dict() for q in interview_doc.question_responses],
                "interview_id": str(interview_doc.id),
                "completion_percentage": interview_doc.completion_percentage,
            }
        )

    # If no existing questions, generate new ones
    resume_path = None
    if db_user.resume:
        try:
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(db_user.resume)

            temp_dir = tempfile.gettempdir()
            resume_path = os.path.join(temp_dir, db_user.resume)

            blob.download_to_filename(resume_path)  # Download file

            logging.info(f"Resume saved at {resume_path}")

        except Exception as e:
            logging.error(f"Failed to fetch resume from GCS: {e}")
            resume_path = None

    try:
        agent_response = openai_utils.generate_initial_question(
            job_role=db_user.job_role,
            company=db_user.field,
            resume=resume_path,
            field=db_user.field,
            years_of_experience=db_user.years_of_experience,
        )
        if isinstance(agent_response, dict):
            if "text" in agent_response:
                parsed = json.loads(agent_response["text"])
            else:
                parsed = agent_response
        else:
            parsed = json.loads(agent_response)
    except Exception as e:
        logging.error("Error generating questions from AI agent: %s", e)
        raise HTTPException(
            status_code=500, detail="Error generating interview questions."
        )
    question_list = parsed["questions"]

    question_responses = []
    for q in question_list:
        question_responses.append(QuestionResponse(question=q))

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
                "review": interview_doc.free_review,
                "user_data": interview_doc.user_data,
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
                        }
                    )

        return JSONResponse(
            content={
                "paid_review": paid_feedback,
                "review": interview_doc.free_review.dict(),
                "user_data": user_data,
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

        if isinstance(raw_paid_feedback, dict) and "text" in raw_paid_feedback:
            paid_feedback = json.loads(raw_paid_feedback["text"])
        elif isinstance(raw_paid_feedback, str):
            paid_feedback = json.loads(raw_paid_feedback)
        else:
            paid_feedback = raw_paid_feedback

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
                        }
                    )

    except Exception as e:
        logging.error("Error generating paid feedback: %s", e)
        raise HTTPException(status_code=500, detail="Error generating paid feedback.")

    interview_doc.paid_review = PaidReview(**paid_feedback)
    await interview_doc.save()

    return JSONResponse(
        content={
            "paid_review": paid_feedback,
            "review": interview_doc.free_review.dict(),
            "user_data": user_data,
        }
    )


# @router.post("/transcribe")
# async def transcribe_audio(
#     question_id: str = Query(...),
#     interview_id: str = Query(...),
#     completion_percentage: str = Query(...),
#     audio: UploadFile = File(...),
#     current_user: str = Depends(auth.get_current_user),
# ):
#     db_user = await User.find_one(User.email == current_user)
#     if not db_user:
#         raise HTTPException(status_code=404, detail="User not found.")
#     try:
#         interview_obj_id = ObjectId(interview_id)
#     except:
#         raise HTTPException(status_code=400, detail="Invalid interview_id")

#     interview_doc = await Interview.get(interview_obj_id)
#     if not interview_doc:
#         raise HTTPException(status_code=404, detail="Interview not found.")

#     try:
#         audio_bytes = await audio.read()
#         audio_file = io.BytesIO(audio_bytes)
#         audio_data, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=None)
#         duration_seconds = librosa.get_duration(y=audio_data, sr=sample_rate)

#     except Exception as e:
#         logging.error("Could not decode audio with librosa. Error: %s", e)
#         raise HTTPException(
#             status_code=400,
#             detail=f"Could not decode audio. Ensure valid format. Error: {str(e)}",
#         )

#     audio_file.seek(0)
#     try:
#         url = "https://api.openai.com/v1/audio/transcriptions"
#         headers = {"Authorization": f"Bearer {openai.api_key}"}
#         data = {
#             "model": "whisper-1",
#         }
#         files = {"file": ("recording.wav", audio_file, "audio/wav")}

#         async with httpx.AsyncClient() as client:
#             response = await client.post(url, headers=headers, data=data, files=files)
#         response_json = response.json()

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"OpenAI Whisper error: {str(e)}")

#     transcript_text = response_json.get("text", "")

#     # Rest of your logic (filler words, fluency score, etc.)
#     filler_list = ["um", "uh", "like", "so", "you know", "er"]
#     transcript_lower = transcript_text.lower()
#     found_fillers = [f for f in filler_list if f in transcript_lower]

#     word_count = len(transcript_text.split())
#     words_per_minute = (
#         (word_count / duration_seconds) * 60 if duration_seconds > 0 else 0.0
#     )

#     filler_count = len(found_fillers)
#     fluency_score = max(0.0, 100.0 - filler_count * 5.0) if word_count else 0.0
#     confidence_score = min(100.0, word_count) if word_count else 0.0
#     clarity_score = max(0.0, 100.0 - filler_count * 3.0) if word_count else 0.0

#     if not interview_doc.question_responses:
#         raise HTTPException(status_code=404, detail="No questions in this interview.")

#     question_found = False
#     for qr in interview_doc.question_responses:
#         if qr.question_id == question_id:
#             # Found the question to update
#             qr.speech_analysis = SpeechAnalysis(
#                 transcript=transcript_text,
#                 fluency_score=fluency_score,
#                 confidence_score=confidence_score,
#                 clarity_score=clarity_score,
#                 words_per_minute=words_per_minute,
#                 filler_words=found_fillers,
#                 time_seconds=duration_seconds,
#             )
#             question_found = True
#             break

#     if not question_found:
#         raise HTTPException(
#             status_code=404, detail="question_id not found in this interview"
#         )
#     interview_doc.completion_percentage = int(completion_percentage)
#     await interview_doc.save()

#     return JSONResponse(
#         content={
#             "message": f"Transcription and analysis complete for question {question_id}",
#         }
#     )


@router.options("/transcribe")
async def options_transcribe():
    response = JSONResponse(
        content={"message": "CORS preflight handled"}, status_code=200
    )
    response.headers["Access-Control-Allow-Origin"] = "https://dev.mockai.tech"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"  # Cache preflight for 24 hours
    return response


@router.post("/transcribe")
async def transcribe_audio(
    question_id: str = Query(...),
    interview_id: str = Query(...),
    completion_percentage: str = Query(...),
    audio: UploadFile = File(...),
    current_user: str = Depends(auth.get_current_user),
):
    # Add request logging
    logging.info(
        f"Transcribe request received - interview_id: {interview_id}, question_id: {question_id}"
    )
    try:
        # User validation
        db_user = await User.find_one(User.email == current_user)
        if not db_user:
            logging.error(f"User not found: {current_user}")
            raise HTTPException(status_code=404, detail="User not found.")

        # Interview validation
        try:
            interview_obj_id = ObjectId(interview_id)
            logging.info(f"Valid ObjectId created: {interview_obj_id}")
        except Exception as e:
            logging.error(
                f"Invalid interview_id format: {interview_id}. Error: {str(e)}"
            )
            raise HTTPException(
                status_code=400, detail=f"Invalid interview_id: {str(e)}"
            )

        interview_doc = await Interview.get(interview_obj_id)
        if not interview_doc:
            logging.error(f"Interview not found with ID: {interview_id}")
            raise HTTPException(status_code=404, detail="Interview not found.")

        # Audio processing
        try:
            audio_bytes = await audio.read()
            logging.info(f"Audio file read, size: {len(audio_bytes)} bytes")

            if len(audio_bytes) == 0:
                logging.error("Empty audio file received")
                raise HTTPException(status_code=400, detail="Empty audio file received")

            audio_file = io.BytesIO(audio_bytes)

            # Check audio format
            try:
                audio_data, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=None)
                duration_seconds = librosa.get_duration(y=audio_data, sr=sample_rate)
                logging.info(
                    f"Audio decoded successfully. Duration: {duration_seconds}s, Sample rate: {sample_rate}Hz"
                )
            except Exception as e:
                logging.error(f"Librosa audio decode error: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not decode audio. Ensure valid format. Error: {str(e)}",
                )

            # OpenAI transcription
            audio_file.seek(0)
            try:
                url = "https://api.openai.com/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {openai.api_key}"}
                logging.info(
                    f"OpenAI API key length: {len(openai.api_key) if openai.api_key else 'No API key'}"
                )

                data = {"model": "whisper-1"}
                files = {"file": ("recording.wav", audio_file, "audio/wav")}

                logging.info("Sending request to OpenAI Whisper API")
                async with httpx.AsyncClient(timeout=30.0) as client:  # Add timeout
                    response = await client.post(
                        url, headers=headers, data=data, files=files
                    )

                # Check response status
                if response.status_code != 200:
                    logging.error(
                        f"OpenAI API error. Status: {response.status_code}, Response: {response.text}"
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"OpenAI API error: {response.text}",
                    )

                response_json = response.json()
                logging.info("OpenAI transcription successful")
            except httpx.TimeoutException:
                logging.error("OpenAI API request timed out")
                raise HTTPException(
                    status_code=504, detail="OpenAI API request timed out"
                )
            except httpx.RequestError as e:
                logging.error(f"OpenAI API request failed: {str(e)}")
                raise HTTPException(
                    status_code=502, detail=f"OpenAI API request failed: {str(e)}"
                )
            except Exception as e:
                logging.error(f"OpenAI Whisper API error: {str(e)}")
                raise HTTPException(
                    status_code=400, detail=f"OpenAI Whisper error: {str(e)}"
                )

            transcript_text = response_json.get("text", "")
            if not transcript_text:
                logging.warning("Empty transcript returned from OpenAI")

            # Analysis logic
            logging.info("Processing speech analysis")
            speech_metrics = analyze_speech(
                transcript_text=transcript_text, duration_seconds=duration_seconds
            )

            # Update interview document
            if not interview_doc.question_responses:
                logging.error(f"No questions found in interview {interview_id}")
                raise HTTPException(
                    status_code=404, detail="No questions in this interview."
                )

            question_found = False
            for qr in interview_doc.question_responses:
                if qr.question_id == question_id:
                    # Found the question to update
                    qr.speech_analysis = SpeechAnalysis(
                        transcript=transcript_text,
                        fluency_score=speech_metrics["fluency_score"],
                        confidence_score=speech_metrics["confidence_score"],
                        clarity_score=speech_metrics["clarity_score"],
                        words_per_minute=speech_metrics["words_per_minute"],
                        filler_words=speech_metrics["found_fillers"],
                        time_seconds=duration_seconds,
                    )
                    question_found = True
                    logging.info(
                        f"Updated question {question_id} with transcript and analysis"
                    )
                    break

            if not question_found:
                logging.error(
                    f"Question ID {question_id} not found in interview {interview_id}"
                )
                raise HTTPException(
                    status_code=404, detail="question_id not found in this interview"
                )

            try:
                interview_doc.completion_percentage = int(completion_percentage)
                await interview_doc.save()
                logging.info(
                    f"Interview {interview_id} saved with updated completion {completion_percentage}%"
                )
            except Exception as e:
                logging.error(f"Error saving interview document: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"Error saving interview: {str(e)}"
                )

            return JSONResponse(
                content={
                    "message": f"Transcription and analysis complete for question {question_id}",
                }
            )

        except HTTPException:
            raise

        except Exception as e:
            logging.error(f"Unhandled exception in transcribe endpoint: {str(e)}")
            import traceback

            logging.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

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
