import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import *
import importlib
import inspect
import asyncio
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "mockai-tech")

client = AsyncIOMotorClient(MONGO_URI)
db = client[MONGO_DB_NAME]


async def initialize_database():
    try:
        # List collection names (await because it's an async operation)
        collections = await db.list_collection_names()
        logging.info(
            f"Connected to database '{MONGO_DB_NAME}'. Collections: {collections}"
        )
    except Exception as e:
        logging.error("Error listing collections: %s", e)

    classes = []
    folder_path = "models"

    # Iterate over all files in the folder
    for filename in os.listdir(folder_path):
        # Check if the file is a Python file
        if filename.endswith(".py") and not filename.startswith("__"):
            # Construct the full file path
            file_path = os.path.join(folder_path, filename)
            # Extract the module name (filename without .py)
            module_name = filename[:-3]
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Iterate over all members of the module
            for name, obj in inspect.getmembers(module):
                # Check if the member is a class and is defined in this module
                if inspect.isclass(obj) and obj.__module__ == module_name:
                    classes.append(eval(f"{module_name}.{name}"))
    logging.info(classes)
    await init_beanie(database=db, document_models=classes)


if __name__ == "__main__":
    asyncio.run(initialize_database())
