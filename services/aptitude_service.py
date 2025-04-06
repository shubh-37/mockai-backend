from bson import ObjectId
from fastapi import Depends, HTTPException, APIRouter, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Optional
import random
from models.aptitude_question import AptitudeQuestion
from models.user_aptitude import UserAptitude
from models.users import User
import schemas, auth

router = APIRouter()


async def get_all_questions(topics: Optional[List[str]] = None):
    # Base query
    query = {}

    # Process topics: if any item contains commas, split it into separate topics
    processed_topics = []
    if topics and len(topics) > 0:
        for topic in topics:
            if "," in topic:
                # Split by comma and add each part as a separate topic
                processed_topics.extend([t.strip() for t in topic.split(",")])
            else:
                processed_topics.append(topic)

        # Apply the processed topics to the query
        query["topic"] = {"$in": processed_topics}
        print(f"Original topics: {topics}")
        print(f"Processed topics: {processed_topics}")

    print(f"Query: {query}")
    questions = await AptitudeQuestion.find(query).to_list()
    if not questions:
        if topics:
            display_topics = processed_topics if processed_topics else topics
            raise HTTPException(
                status_code=404,
                detail=f"No questions found for the selected topics: {', '.join(display_topics)}",
            )
        else:
            raise HTTPException(
                status_code=404, detail="No questions found in the database"
            )
    print(f"Found {len(questions)} questions")
    for question in questions:
        question.id = str(question.id)
    return questions


def get_balanced_quiz(
    questions: List[AptitudeQuestion],
    total_questions: int,
    topics: Optional[List[str]] = None,
):
    processed_topics = []
    if topics and len(topics) > 0:
        for topic in topics:
            if "," in topic:
                # Split by comma and add each part as a separate topic
                processed_topics.extend([t.strip() for t in topic.split(",")])
            else:
                processed_topics.append(topic)

    if not processed_topics or len(processed_topics) == 0:
        available_topics = [
            "Verbal & Reading Comprehension",
            "Logical Reasoning",
            "Numerical Reasoning",
        ]
    else:
        available_topics = processed_topics

    # Group questions by level and topic
    grouped_questions: Dict[str, Dict[str, List[AptitudeQuestion]]] = {
        "Easy": {topic: [] for topic in available_topics},
        "Medium": {topic: [] for topic in available_topics},
        "Hard": {topic: [] for topic in available_topics},
    }

    # Populate grouped_questions with questions that match the selected topics
    for question in questions:
        if question.topic in available_topics:
            grouped_questions[question.level][question.topic].append(question)

    # Calculate the number of questions to select from each category
    num_topics = len(available_topics)
    num_levels = 3  # Easy, Medium, Hard

    # Calculate questions per level, ensuring we get all questions
    questions_per_level = total_questions // num_levels
    remainder_levels = (
        total_questions % num_levels
    )  # Remainder to distribute across levels

    balanced_quiz = []

    # Process each level
    for i, level in enumerate(["Easy", "Medium", "Hard"]):
        # Add an extra question to this level if we have remainder
        current_level_questions = questions_per_level
        if i < remainder_levels:
            current_level_questions += 1

        # Calculate how many questions per topic for this level
        if num_topics == 1:
            questions_per_topic = current_level_questions  # All to one topic
        else:
            # Distribute questions per topic more carefully
            base_per_topic = current_level_questions // num_topics
            remainder_topics = current_level_questions % num_topics

            # Create a list of how many questions to take from each topic
            questions_per_topic_list = []
            for j in range(num_topics):
                if j < remainder_topics:
                    questions_per_topic_list.append(base_per_topic + 1)
                else:
                    questions_per_topic_list.append(base_per_topic)

        # Add questions for each topic
        for t_idx, topic in enumerate(available_topics):
            # Get questions for the current level and topic
            available_questions = grouped_questions[level][topic]

            # Get the number of questions needed for this topic
            if num_topics == 1:
                needed_questions = questions_per_topic  # Using the integer directly
            else:
                needed_questions = questions_per_topic_list[
                    t_idx
                ]  # Using the list we created

            if len(available_questions) < needed_questions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough questions for level '{level}' and topic '{topic}'. Need {needed_questions}, but have {len(available_questions)}.",
                )

            # Randomly sample the required number of questions
            sampled_questions = random.sample(available_questions, needed_questions)
            balanced_quiz.extend(sampled_questions)

    # Shuffle the final quiz to ensure randomness
    random.shuffle(balanced_quiz)

    # Double-check we have the exact number needed
    if len(balanced_quiz) != total_questions:
        raise ValueError(
            f"Expected {total_questions} questions but got {len(balanced_quiz)}. This should not happen."
        )

    return balanced_quiz


@router.get("/15", response_model=List[AptitudeQuestion])
async def get_15_question_quiz(
    topics: Optional[List[str]] = Query(None),
    current_user: str = Depends(auth.get_current_user),
):
    questions = await get_all_questions(topics)
    quiz = get_balanced_quiz(questions, 15, topics)
    return JSONResponse(content=[q.dict() for q in quiz])


@router.get("/30", response_model=List[AptitudeQuestion])
async def get_30_question_quiz(
    topics: Optional[List[str]] = Query(None),
    current_user: str = Depends(auth.get_current_user),
):
    questions = await get_all_questions(topics)
    quiz = get_balanced_quiz(questions, 30, topics)
    return JSONResponse(content=[q.dict() for q in quiz])


@router.post("/submit", response_model=dict)
async def submit_quiz_result(
    quiz_data: schemas.QuizSubmissionRequest,
    current_user: str = Depends(auth.get_current_user),
):

    user = await User.find_one(User.email == current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_aptitude = UserAptitude(
        correct_no_of_questions=quiz_data.correct_no_of_questions,
        wrong_no_of_answers=quiz_data.wrong_no_of_answers,
        score=quiz_data.score,
        user_id=user,
        topics=quiz_data.topics,
    )
    await user_aptitude.insert()
    return JSONResponse(content="Quiz response submitted successfully.")


@router.get("/scores", response_model=List[UserAptitude])
async def get_user_quiz_responses(current_user: str = Depends(auth.get_current_user)):

    user = await User.find_one(User.email == current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch all quiz responses for the user
    quiz_responses = await UserAptitude.find(
        UserAptitude.user_id.id == user.id
    ).to_list()
    serialized_responses = []
    for response in quiz_responses:
        # Extract only the required fields and handle possibly missing fields
        serialized_response = {
            "topics": response.topics if hasattr(response, "topics") else [],
            "score": response.score,
            "created_at": (
                response.created_at.isoformat() if response.created_at else None
            ),
        }
        serialized_responses.append(serialized_response)

    return JSONResponse(content=serialized_responses)
