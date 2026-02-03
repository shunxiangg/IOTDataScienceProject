import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

app = FastAPI()

# Allow frontend (localhost) to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatIn(BaseModel):
    message: str

@app.post("/chat")
def chat(body: ChatIn):
    user_msg = body.message.strip()
    if not user_msg:
        return {"reply": "Please type something."}

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Keep replies clear and not too long."},
            {"role": "user", "content": user_msg}
        ]
    )
    reply = resp.choices[0].message.content
    return {"reply": reply}
