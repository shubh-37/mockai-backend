import pandas as pd
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from typing import List, Dict, Any
import os
import numpy as np

from models.aptitude_question import AptitudeQuestion


async def init_db():
    """Initialize the database connection."""
    # Get MongoDB connection string from environment variable or use default
    mongo_connection_string = os.getenv("MONGO_URI")

    # Create Motor client
    client = AsyncIOMotorClient(mongo_connection_string)

    # Get database name from env or use default
    db_name = os.getenv("MONGODB_DB_NAME", "prepsom")

    # Initialize beanie with the document models
    await init_beanie(database=client[db_name], document_models=[AptitudeQuestion])

    print(f"Connected to MongoDB database: {db_name}")
    return client


def process_excel_data(file_path: str) -> List[Dict[str, Any]]:
    """
    Process data from all sheets in the Excel file,
    assuming each question and its options are on a single row.

    Expected columns (case-insensitive):
      - "question" in the header for the question text
      - "(A)" or "a)" or similar for option A
      - "(B)" or "b)" or similar for option B
      - "(C)" ...
      - "(D)" ...
      - "answer" for the correct answer (optional, defaults to "A" if missing)
      - "level" or "difficulty" for question level (optional, defaults to "Easy" if missing)

    Args:
        file_path: Path to the Excel file

    Returns:
        A list of dictionaries with processed data ready for MongoDB
    """
    # Load the Excel file
    excel_file = pd.ExcelFile(file_path)
    sheet_names = excel_file.sheet_names
    print(f"Found {len(sheet_names)} sheets: {', '.join(sheet_names)}")

    all_data = []

    # Go through each sheet
    for sheet_name in sheet_names:
        topic = sheet_name  # We'll treat the sheet name as the "topic"
        print(f"\nProcessing sheet: {sheet_name} (Topic: {topic})")

        # Read the sheet into a DataFrame
        df = pd.read_excel(excel_file, sheet_name=sheet_name)

        # Standardize column names: strip spaces, make lowercase
        df.columns = [col.strip().lower() for col in df.columns]
        print(f"Columns found: {list(df.columns)}")

        # Identify key columns
        # 1) Question column
        question_col = next((c for c in df.columns if "question" in c), None)
        if not question_col:
            print(
                f"Warning: No 'question' column found in sheet '{sheet_name}'. Skipping..."
            )
            continue

        # 2) Option columns
        #    We'll look for columns containing "(a)", "a)", etc. in their names
        #    Adjust these patterns if your actual headers differ
        possible_a_cols = ["(a)", "a)", "a", "option a"]
        possible_b_cols = ["(b)", "b)", "b", "option b"]
        possible_c_cols = ["(c)", "c)", "c", "option c"]
        possible_d_cols = ["(d)", "d)", "d", "option d"]

        def find_col(possible_names):
            return next(
                (c for c in df.columns if any(name == c for name in possible_names)),
                None,
            )

        a_col = find_col(possible_a_cols)
        b_col = find_col(possible_b_cols)
        c_col = find_col(possible_c_cols)
        d_col = find_col(possible_d_cols)

        # If any option column is missing, we'll just skip that sheet or store fewer options
        # but ideally your sheet has all four columns
        if not all([a_col, b_col, c_col, d_col]):
            print(
                "Warning: Not all of (A), (B), (C), (D) columns found. Some options may be missing."
            )

        # 3) Answer column
        answer_col = next((c for c in df.columns if "answer" in c), None)

        # 4) Level/difficulty column
        level_col = next(
            (c for c in df.columns if "level" in c or "difficulty" in c), None
        )

        # Prepare to store questions from this sheet
        questions = []

        # Iterate over each row in the DataFrame
        for idx, row in df.iterrows():
            # Skip blank or NaN questions
            if pd.isna(row[question_col]) or not str(row[question_col]).strip():
                continue

            question_text = str(row[question_col]).strip()

            # Gather options (A/B/C/D) if columns exist
            # We'll label them (A), (B), etc. in the final "options" list
            options = []
            if a_col and pd.notna(row[a_col]):
                options.append(f"{row[a_col]}")
            if b_col and pd.notna(row[b_col]):
                options.append(f"{row[b_col]}")
            if c_col and pd.notna(row[c_col]):
                options.append(f"{row[c_col]}")
            if d_col and pd.notna(row[d_col]):
                options.append(f"{row[d_col]}")

            # Get the answer (default "A" if missing)
            answer_val = (
                str(row[answer_col]).strip()
                if answer_col and pd.notna(row[answer_col])
                else "A"
            )

            # Get the level (default "Easy" if missing)
            level_val = (
                str(row[level_col]).strip()
                if level_col and pd.notna(row[level_col])
                else "Easy"
            )

            # Build the question dict
            if question_text and options:
                question_dict = {
                    "question": question_text,
                    "options": options,
                    "answer": answer_val,
                    "level": level_val,
                    "topic": topic,
                }
                questions.append(question_dict)

        print(f"Processed {len(questions)} questions from sheet '{sheet_name}'")

        # Show a sample question for debugging
        if questions:
            print("Sample processed question:")
            sample = questions[0]
            print(f"Question: {sample['question']}")
            print(f"Options: {sample['options']}")
            print(f"Answer: {sample['answer']}")
            print(f"Level: {sample['level']}")

        # Add to the global list
        all_data.extend(questions)

    return all_data


async def save_to_mongodb(data_list: List[Dict[str, Any]]):
    """
    Save the processed data to MongoDB.

    Args:
        data_list: List of dictionaries with question data
    """
    questions_saved = 0

    for data in data_list:
        # Make sure required fields are present
        if (
            not data.get("question")
            or not data.get("options")
            or not data.get("answer")
        ):
            print(
                f"Skipping incomplete question: {data.get('question', 'No question text')[:30]}..."
            )
            continue

        # Create a new AptitudeQuestion instance
        question = AptitudeQuestion(
            question=data["question"],
            options=data["options"],
            answer=data["answer"],
            level=data["level"],
            topic=data["topic"],
        )

        # Save to database
        await question.save()
        questions_saved += 1

        # Print progress every 10 questions
        if questions_saved % 10 == 0:
            print(f"Saved {questions_saved} questions so far...")

    print(f"Successfully saved {questions_saved} questions to MongoDB")


async def main():
    """Main function to orchestrate the data migration."""
    excel_file_path = os.path.abspath("formatted_aptitude_questions.xlsx")

    # Initialize database
    client = await init_db()

    try:
        # Process Excel data
        print(f"Processing Excel file: {excel_file_path}")
        processed_data = process_excel_data(excel_file_path)

        # Save data to MongoDB
        print(f"Saving {len(processed_data)} questions to MongoDB...")
        await save_to_mongodb(processed_data)

        print("Data migration completed successfully!")

    except Exception as e:
        print(f"Error during data migration: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Close the MongoDB connection
        client.close()
        print("MongoDB connection closed")


if __name__ == "__main__":
    asyncio.run(main())
