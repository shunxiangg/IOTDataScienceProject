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

The backend stores booking sessions in:
```
backend\booking_store.json
```
Clinic knowledge base lives in:
```
backend\clinic_kb.json
```
You can manage bookings via:
- `GET /bookings?session_id=...`
- `DELETE /bookings/{id}?session_id=...`
- `POST /history/clear?session_id=...`

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

## GitHub Pages Hosting (Frontend Only)

Use GitHub Pages to host the **frontend**. The backend must already be hosted (AWS Lambda + API Gateway).

### 1) Use the `frontend` folder
This repo already has a `frontend` folder. GitHub Pages can serve directly from it.

### 2) Set the API URL
Edit `frontend\main.js` and set:
```js
const API_URL = "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/chat";
```

### 3) Keep backend folder in the same repo
You can keep `backend/` in the same repo. GitHub Pages only serves the `frontend/` folder.

### 4) Enable GitHub Pages
1. Open your GitHub repo → **Settings** → **Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select the branch (e.g., `main`) and folder (`/frontend`), then **Save**.
4. GitHub will show a public URL like:
   ```
   https://<your-username>.github.io/<repo-name>/
   ```

### 5) Test
Open the GitHub Pages URL. You should be able to chat with the bot.

### Notes
- GitHub Pages is static hosting only; it cannot run the backend.
- If you change the API URL, re‑commit and push.

## Vercel Deployment (No Backend Setup Required) ⚡

Deploy everything on Vercel with serverless functions. No local backend needed!

### 1) Prerequisites
- Vercel account (free at https://vercel.com)
- GitHub account with your repo
- OpenAI API key

### 2) Connect GitHub to Vercel
1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click **Add New...** → **Project**
3. Select **Import Git Repository**
4. Connect your GitHub account and select this repo

### 3) Add Environment Variables
1. In Vercel, go to **Settings** → **Environment Variables**
2. Add:
   - **Name**: `OPENAI_API_KEY`
   - **Value**: Your OpenAI API key
3. Click **Save**

### 4) Deploy
1. Click **Deploy**
2. Vercel automatically detects `package.json` and `vercel.json`
3. The build process installs dependencies and deploys

### 5) Access Your Bot
Vercel provides a public URL like:
```
https://your-project.vercel.app
```

The bot is now live! No backend server needed—everything runs on Vercel serverless functions.

### How It Works
- **Frontend**: Served by Vercel (Next.js/static files)
- **API**: Node.js serverless functions in `/api` directory
- **Storage**: `/tmp` on function runtime (session-based)
- **API Key**: Secure environment variable (never exposed to frontend)

### Updating After Deployment
1. Make changes locally
2. Push to GitHub
3. Vercel auto-deploys on push

### Notes
- The `/tmp` directory on Vercel functions is ephemeral (cleared between invocations)
- For persistent storage, integrate a database (Supabase, MongoDB, etc.)
- OpenAI API key is securely stored as an environment variable

