from openai import OpenAI
import os
import logging
import aiofiles

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def delete_file(vs_id, file_id):
    openai_client.beta.vector_stores.files.delete(
        vector_store_id=vs_id,
        file_id=file_id,
        timeout=5
    )
    openai_client.files.delete(file_id, timeout=5)

def upload_file(email):
    file = open(os.path.join('tmp_files', f'{email}_resume.pdf'), 'rb')
    response = openai_client.files.create(
        file=file,
        purpose='assistants',
        timeout=5
    )
    file.close()
    return response.id

def create_vector_store(email):
    response = openai_client.beta.vector_stores.create(
        name=f"VS for {email}",
        timeout=5
    )
    return response.id

def add_file_to_vector_store(vs_id, file_id):
    openai_client.beta.vector_stores.files.create(
        vector_store_id=vs_id,
        file_id=file_id,
        timeout=5
    )

def get_gpt_response(thread_id, assistant_id, content):
    try:
        openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )
        openai_client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id, 
            timeout=5
        )
        # List messages in the thread
        messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
        # Display the assistant's response
        msgs = []
        for msg in messages:
            if msg.role == "assistant":
                msgs.append(msg.content)
        logging.info(f"{msgs[0][0].text.value}")
        return msgs[0][0].text.value
    except Exception as e:
        logging.info(f"Error communicating with OpenAI API: {e}")
        raise Exception(e)

def get_interview_feedback(thread_id, assistant_id, qaa):
    return get_gpt_response(thread_id, assistant_id, f"""Evaluate the candidate's interview performance based on their answers to the questions asked. Below are the user provided answers to the mentioned questions in array format:
    {qaa}

    If the user has not given enough answer or answer is not good enough, please rate accordingly. You can use below points to evaluate and provide feedback:
    1. check whether the array is empty or not. if empty, provide poor score.
    2. check if answer is not empty or null, otherwise rate accordingly.
    3. check if answer is not too short and genuine.

    
    Provide feedback in the following JSON format:
    {{
        "overall_score": "<score from 1 to 10>",
        "speech": "<evaluation of communication clarity and fluency, rated 1 to 10>",
        "confidence": "<evaluation of the candidate's confidence, rated 1 to 10>",
        "technical_skills": "<evaluation of technical skills based on responses, rated 1 to 10>",
        "areas_of_improvement": "<provide 3 specific and actionable suggestions for improvements>"
    }}
    On scale of 1 to 10, 1 is lowest and 10 is highest. Focus on providing constructive, actionable feedback for each area/concept. Be objective and concise. Output in JSON format only.""")

def start_interview(thread_id, assistant_id, interview_input, full_name):
    return get_gpt_response(thread_id, assistant_id, f"""Generate responses for each of the prompts given below. Ask questions to candidate named "{full_name}". Ask each question by acknowledging the previous one i.e. start next question with something like okay, so next let's discuss on.., thank you for sharing that.., etc. Use candidate name while asking each question to make it more engaging.

1. Start the interview for Role: {interview_input["job_role"]}
2. Ask next question.
3. Ask a question for Company: {interview_input["company"]}, Role: {interview_input["job_role"]} , Difficulty: {interview_input["difficulty"]}, Category: Basic.
4. Ask a situational question for Company: {interview_input["company"]}, Role: {interview_input["job_role"]} , Difficulty: {interview_input["difficulty"]}.
5. Ask a question for Company: {interview_input["company"]}, Role: {interview_input["job_role"]} , Difficulty: {interview_input["difficulty"]}, Category: Technical.
6. Based on question number 5, ask a follow up question.
7. Based on question number 6, ask next question.
8. Ask a question for Company: {interview_input["company"]}, Role: {interview_input["job_role"]} , Difficulty: {interview_input["difficulty"]}, Category: Technical.
9. Based on question number 8, ask a follow up question.
10. Ask a closing question for Company: {interview_input["company"]}, Role: {interview_input["job_role"]} , Difficulty: {interview_input["difficulty"]}.

Generate responses in JSON format containing questions as list. Output JSON directly.""")

def create_thread_specific_assistant(email, vector_store_id):
    logging.info(f"Creating assistant for user: {email}")
    assistant = openai_client.beta.assistants.create(
        name=f"PrepSom Companion for {email}",
            instructions=f"""You are an AI interviewer designed to evaluate candidates based on his/her resume, role, years of experience and company. Your goal is to conduct a realistic and structured interview. You should act as similar to human as possible. Use the candidate's resume (stored in the vector store) to tailor your questions if needed. After asking 10 questions end the interview. Ask one question at a time. Be interactive but not much. Don't give feedback while taking interview. Start the interview by asking the candidate to give introduction followed by why they chose to be in this particular field. Then ask technical questions that the candidate might have studied to pursue the profession followed by what you feel is best. Leverage context from the thread to craft better and more specific follow-up questions. Prioritize engaging, insightful, and job-relevant inquiries throughout the interview. Use candidate name while asking each question to make it more engaging.""",
            model="ft:gpt-4o-2024-08-06:prepsom:prepsom:AoxJegqD",
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
    )
    return assistant

def create_user_thread_and_assistant(email):
    user_thread = openai_client.beta.threads.create(timeout=5)
    logging.info(f"Thread created for user {email}")
    vs_id = create_vector_store(email)
    assistant = create_thread_specific_assistant(email, vs_id)
    return user_thread.id, assistant.id, vs_id

async def add_file_to_vs(email, resume, vs_id):
    # TODO: validate resume whether it is not a malicious file
    async with aiofiles.open(os.path.join('tmp_files', f'{email}_resume.pdf'), 'wb') as out_file:
        while content := await resume.read(1024):  # async read chunk
            await out_file.write(content)  # async write chunk
    file_id = upload_file(email)
    os.remove(os.path.join('tmp_files', f'{email}_resume.pdf'))
    add_file_to_vector_store(vs_id, file_id)
    return file_id
