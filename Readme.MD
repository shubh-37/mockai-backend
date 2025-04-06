## PrepSOM (Backend)

Run below steps to start the server:
1. Clone the repo using git clone.
2. Change directory to the repo.
3. pip3 install virtualenv
4. python3 -m venv venv
5. source ./venv/bin/activate (for linux)
   venv\Scripts\activate (for windows)
6. pip3 install -r requirements.txt
7. export OPENAI_API_KEY="" (for linux)
   set OPENAI_API_KEY="" (for windows)
8. uvicorn main:app --host 0.0.0.0 --port 8000 --log-config logging.conf --ssl-keyfile certs\key.pem --ssl-certfile certs\cert.pem