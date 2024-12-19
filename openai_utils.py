from openai import OpenAI
import os
import logging
import aiofiles

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def upload_file_for_thread(thread_id):
    
    response = openai_client.files.create(
        file=open(os.path.join('tmp_files', f'{thread_id}_resume.pdf'), 'rb'),
        purpose='assistants'
    )
    # print(response)
    # TODO: delete temp resume file
    return response.id

def create_vector_store(thread_id):
    response = openai_client.beta.vector_stores.create(
        name=f"Vector Store for {thread_id}",
        # description=f"Resume for user id: {thread_id}."
    )
    return response.id

def add_file_to_vector_store(vector_store_id, file_id):
    openai_client.beta.vector_stores.file_batches.create_and_poll(
        vector_store_id=vector_store_id,
        file_ids=[file_id]
    )

def converse(thread_id, assistant_id, input_context):
        """
        Sends user input to OpenAI and gets a response.
        """
        try:
            message = openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role=input_context["role"],
                content=input_context["content"],
            )
            run = openai_client.beta.threads.runs.create_and_poll(
                thread_id=thread_id,
                assistant_id=assistant_id,
            )
            logging.info(run)
            # List messages in the thread
            messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
            # Display the assistant's response
            msgs = []
            for msg in messages:
                if msg.role == "assistant":
                    logging.info(f"Assistant: {msg.content}")
                    msgs.append(msg.content)
            return msgs[0][0].text.value
        except Exception as e:
            logging.info(f"Error communicating with OpenAI API: {e}")
            return "I'm sorry, I couldn't process that."

def create_thread_specific_assistant(user_id, vector_store_id, job_role, industry, overall_experience_yrs):
    logging.info(f"Creating assistant for thread id: {user_id}")
    assistant = openai_client.beta.assistants.create(
        name="Interview Companion - PrepSom",
            # TODO: explore timer in chatgpt
            # TODO: Improve promts
            instructions=f"""
            You are an AI interviewer designed to evaluate candidates for specific job roles based on their resume, job role, and job description. Your goal is to conduct a realistic and structured interview using the provided inputs: Job Role ({job_role}), Industry ({industry}), Overall Experienece ({overall_experience_yrs} years). Use the candidate's resume (stored in the vector store) to tailor your questions. Follow these evaluation criteria and guidelines:

            Interview Sections:
            1. Personality Assessment (25% weight):
                - Ask questions about the candidate's background, motivations, and interpersonal skills.
                - Evaluate their confidence, communication clarity, and articulation.
            2. Technical and Industry-Relevant Assessment (25% weight):
                - Create questions aligned with the key skills, knowledge, and trends outlined in the job description.
                - Test the candidate's understanding of technical concepts and practical applications.
                - Evaluate the interview based on below skills if the role is investment or finance based:
                    -- Good Financial modelling skills.
                    -- The candidate should be comfortable the three Financial statements and how they link with each other.
                    -- The candidate should be good with excel skills.
                    -- The candidate understands how DCF works.
                    -- The candidate understands how depreciation and amortization calculation works.
                    -- The candidate should be able to construct cash flow statement.
            3. Resume-Based Questions (25% weight):
                - Ask specific questions about the candidate's past experiences, achievements, and roles mentioned in their resume.
                - Evaluate their ability to relate past experiences to the requirements of the job role.
            4. Adaptability and Critical Thinking (25% weight):
                - Pose situational or behavioral questions to assess problem-solving skills and adaptability.

            Interview Guidelines:
            1. Keep the interview realistic and professional.
            2. Ask 7 questions in the interview. After asking the last question, end the interview with greeting.
            3. Begin asking questions only when the user says "Start the interview".
            4. Ask one question at a time and wait for the candidate's response before proceeding.
            5. Use the candidate's resume and job description context to ask customized and meaningful questions.
            6. Start the interview by asking the candidate to give introduction followed by why they chose to be in this particular field. Then ask technical questions that the candidate might have studied to pursue the profession followed by what you feel is best.
            7. Don't give feedback on the questions answered while the interview is going on.
            8. Ask learnings from the project mentioned in the resume.
            9. Don't ask questions together, ask one by one. 
            10. Don't combine 2 questions together.
            11. Ask 7 questions only. 
            12. Leverage context from the thread to craft better and more specific follow-up questions. 
            13. Prioritize engaging, insightful, and job-relevant inquiries throughout the interview.
            """,
            model="gpt-4-turbo",
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
    )
    return assistant

async def create_user_thread_and_assistant(username, resume, job_role, industry, overall_experience_yrs):
    user_thread = openai_client.beta.threads.create()
    # TODO: validate resume whether it is not a malicious file
    async with aiofiles.open(os.path.join('tmp_files', f'{user_thread.id}_resume.pdf'), 'wb') as out_file:
        while content := await resume.read(1024):  # async read chunk
            await out_file.write(content)  # async write chunk
    file_id = upload_file_for_thread(user_thread.id)
    vector_store_id = create_vector_store(user_thread.id)
    add_file_to_vector_store(vector_store_id, file_id)
    assistant = create_thread_specific_assistant(username, vector_store_id, job_role, industry, overall_experience_yrs)
    return user_thread.id, assistant.id