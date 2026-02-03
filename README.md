# IOT Data Science Project

Simple OpenAI chat demo with:
- Local FastAPI backend + static frontend
- AWS Lambda backend + S3-hosted frontend

## Prerequisites
- Python 3.10+
- An OpenAI API key

## Local Run (FastAPI + Static Frontend)

### 1) Backend
Create and activate a virtual environment, install dependencies, and run the API.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

You should see:
```
Uvicorn running on http://127.0.0.1:8000
```

Create `backend\.env` with:
```
OPENAI_API_KEY=YOUR_OPENAI_KEY_HERE
```

### 2) Frontend
Serve the static frontend:

```powershell
cd frontend
python -m http.server 5500
```

Open:
```
http://127.0.0.1:5500
```

## AWS Lambda Backend

The Lambda handler lives in `lambda-backend\lambda_function.py` and expects `OPENAI_API_KEY` as an environment variable.

To build the deployment zip:

```powershell
cd lambda-backend
.\build_zip.ps1
```

This produces `lambda-backend\openai_lambda.zip`.

## S3 Frontend (API Gateway)

Static frontend for API Gateway lives in `web-frontend-s3`.
Update the API endpoint in:

```
web-frontend-s3\main.js
```

Set:
```
const API_URL = "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/chat";
```
