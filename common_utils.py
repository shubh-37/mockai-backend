import requests
import fitz
import tempfile
import os
import logging
import re

def extract_resume_text_from_s3_url(resume_url: str, char_limit: int = 3000) -> str:
    try:
        response = requests.get(resume_url, timeout=10)
        if response.status_code != 200:
            raise Exception(f"Failed to download resume: HTTP {response.status_code}")

        temp_path = os.path.join(tempfile.gettempdir(), "temp_resume.pdf")
        with open(temp_path, "wb") as f:
            f.write(response.content)

        text = ""
        with fitz.open(temp_path) as doc:
            for page in doc:
                text += page.get_text()

        return text[:char_limit]

    except Exception as e:
        logging.error(f"Error processing resume from S3: {e}")
        return ""


def extract_json_from_llm_text(text: str) -> str:
    """Strip markdown code blocks and extract clean JSON."""
    if not text:
        return ""

    # Remove markdown-style triple backticks and optional 'json'
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()

    return text
