import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def _resp(status_code: int, body: dict):
    # CORS headers so browser (S3 site) can call API Gateway
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # for demo; lock down later
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,POST"
        },
        "body": json.dumps(body)
    }

def lambda_handler(event, context):
    # API Gateway HTTP API sends method here:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    # Handle CORS preflight
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    try:
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)

        user_msg = (body.get("message") or "").strip()
        if not user_msg:
            return _resp(400, {"error": "message is required"})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Keep replies clear and not too long."},
                {"role": "user", "content": user_msg}
            ]
        )

        reply = resp.choices[0].message.content
        return _resp(200, {"reply": reply})

    except Exception as e:
        return _resp(500, {"error": str(e)})
