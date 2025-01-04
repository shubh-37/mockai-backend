from pymongo import MongoClient
import os
import logging

# Load environment variables (AWS configuration should be handled in your environment)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

client = MongoClient(MONGO_URI)
db = client['prepsom_db']  # Connect to the database
logging.info(db.list_collection_names())  # Test connection
users_collection = db['users']  # Users collection

