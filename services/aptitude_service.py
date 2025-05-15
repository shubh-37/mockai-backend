from bson import ObjectId
from fastapi import Depends, HTTPException, APIRouter, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Optional
import random
import re
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
    questions_with_answers = await AptitudeQuestion.find(query).to_list()

    if not questions_with_answers:
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

    print(f"Found {len(questions_with_answers)} questions")

    # Create a new list instead of modifying the one we're iterating over
    questions_without_answers = []
    for question in questions_with_answers:
        question.id = str(question.id)
        question_dict = question.dict()
        question_dict.pop("answer", None)  # Remove the answer field
        questions_without_answers.append(question_dict)
    return questions_without_answers


def get_balanced_quiz(
    questions: List,
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
            "Data Structures & Algorithm",
        ]
    else:
        available_topics = processed_topics

    # Group questions by level and topic
    grouped_questions: Dict[str, Dict[str, List]] = {
        "Easy": {topic: [] for topic in available_topics},
        "Medium": {topic: [] for topic in available_topics},
        "Hard": {topic: [] for topic in available_topics},
    }

    # Populate grouped_questions with questions that match the selected topics
    for question in questions:
        if question["topic"] in available_topics:
            grouped_questions[question["level"]][question["topic"]].append(question)

    balanced_quiz = []
    num_topics = len(available_topics)

    # First, determine questions per topic according to the required distribution
    if num_topics == 1:
        # All questions go to the single topic
        questions_per_topic = [total_questions]
    elif num_topics == 2:
        # For 2 topics: Split questions with first topic getting the remainder
        base = total_questions // 2
        # For 15 questions: 8 and 7
        # For 30 questions: 15 and 15
        questions_per_topic = [base + (total_questions % 2), base]
    elif num_topics == 3:
        # For 3 topics: Equal distribution with any remainder going to first topics
        base = total_questions // 3
        remainder = total_questions % 3
        questions_per_topic = [
            base + (1 if i < remainder else 0) for i in range(num_topics)
        ]
    else:
        # Generic case for more topics if ever needed
        base = total_questions // num_topics
        remainder = total_questions % num_topics
        questions_per_topic = [
            base + (1 if i < remainder else 0) for i in range(num_topics)
        ]

    # Now, for each topic, divide the questions evenly across difficulty levels
    for topic_idx, topic in enumerate(available_topics):
        topic_question_count = questions_per_topic[topic_idx]

        # Determine questions per level for this topic
        base_per_level = topic_question_count // 3  # 3 levels: Easy, Medium, Hard
        remainder_levels = topic_question_count % 3

        questions_per_level = [
            base_per_level + (1 if i < remainder_levels else 0) for i in range(3)
        ]

        # Get questions for each level
        for level_idx, level in enumerate(["Easy", "Medium", "Hard"]):
            needed_questions = questions_per_level[level_idx]
            available_questions = grouped_questions[level][topic]

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
    return JSONResponse(content=quiz)


@router.get("/30", response_model=List[AptitudeQuestion])
async def get_30_question_quiz(
    topics: Optional[List[str]] = Query(None),
    current_user: str = Depends(auth.get_current_user),
):
    questions = await get_all_questions(topics)
    quiz = get_balanced_quiz(questions, 30, topics)
    return JSONResponse(content=quiz)


@router.post("/submit", response_model=dict)
async def submit_quiz_result(
    quiz_data: schemas.QuizSubmissionRequest,
    current_user: str = Depends(auth.get_current_user),
):
    user = await User.find_one(User.email == current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Extract submitted answers and topics
    answers = quiz_data.answers
    topics = quiz_data.topics

    # Fetch all the questions that were in the quiz to compare answers
    question_ids = list(answers.keys())
    quiz_questions = await AptitudeQuestion.find(
        {"_id": {"$in": [ObjectId(qid) for qid in question_ids]}}
    ).to_list()

    # Create a dictionary for easy lookup of correct answers
    question_map = {str(q.id): q for q in quiz_questions}

    # Calculate score and prepare results
    correct_answers = 0
    wrong_answers = 0
    unanswered = 0
    results = []

    for question_id, user_answer in answers.items():
        # Skip if the question is not found in our database
        if question_id not in question_map:
            continue

        # Get the correct answer for this question
        correct_option = question_map[question_id].answer  # Format: (A), (B), etc.

        # Get user's selected option
        selected_option = user_answer.get("selectedOption")

        result = {
            "question_id": question_id,
            "correct_answer": correct_option,
            "selected_option": selected_option,
        }

        if selected_option is None:
            unanswered += 1
            result["isCorrect"] = False
        else:
            # Extract the letter from the selected option using regex
            match = re.search(r"\((.)\)", selected_option)
            if match:
                selected_letter = match.group(1)  # Just 'A', 'B', etc.

                # Compare directly with correct_option (which is also 'A', 'B', etc.)
                is_correct = selected_letter == correct_option
                result["isCorrect"] = is_correct

                if is_correct:
                    correct_answers += 1
                else:
                    wrong_answers += 1
            else:
                wrong_answers += 1
                result["isCorrect"] = False

        results.append(result)

    # Calculate final score
    total_questions = len(quiz_questions)
    total_score = (
        (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    )

    # Create and save user aptitude record
    user_aptitude = UserAptitude(
        correct_no_of_questions=correct_answers,
        wrong_no_of_answers=wrong_answers,
        score=total_score,
        user_id=user,
        topics=topics,
    )
    await user_aptitude.insert()

    return JSONResponse(
        content={
            "message": "Quiz response submitted successfully.",
            "score": round(total_score, 2),  # Round score to 2 decimal places
            "correct_answers": correct_answers,
            "wrong_answers": wrong_answers,
            "unanswered": unanswered,
            "total_questions": total_questions,
            "results": results,
        }
    )


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
