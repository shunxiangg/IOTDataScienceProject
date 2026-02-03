import os
import json
import re
from difflib import SequenceMatcher
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Header
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
    session_id: str | None = None

STORE_PATH = Path(__file__).resolve().parent / "booking_store.json"
KB_PATH = Path(__file__).resolve().parent / "clinic_kb.json"

def _load_store() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_store(store: dict) -> None:
    STORE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=True), encoding="utf-8")

def _load_kb() -> dict:
    if not KB_PATH.exists():
        return {}
    try:
        return json.loads(KB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _format_booking(booking: dict) -> str:
    if not booking:
        return "No booking found yet."
    lines = []
    btype = booking.get("booking_type") or "unknown"
    lines.append(f"**Booking type:** {btype}")
    details = booking.get("details") or {}
    for k, v in details.items():
        if v:
            lines.append(f"**{k}:** {v}")
    status = booking.get("status")
    if status:
        lines.append(f"**status:** {status}")
    return "\n".join(lines)

REQUIRED_FIELDS = ["service", "date", "time", "location", "contact"]

def _new_draft() -> dict:
    return {
        "booking_type": "appointment",
        "details": {},
        "status": "draft",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "missing_fields": [],
        "last_field": "",
        "pending_field": "",
        "pending_value": "",
        "awaiting_confirmation": False,
        "confirmation_summary": ""
    }

def _missing_fields(draft: dict) -> list:
    details = draft.get("details") or {}
    return [f for f in REQUIRED_FIELDS if not str(details.get(f, "")).strip()]

def _question_for(field: str, kb: dict) -> str:
    if field == "service":
        services = [s.get("name") for s in (kb.get("services") or []) if s.get("name")]
        if services:
            return "What service would you like to book? Options: " + ", ".join(services)
        return "What service would you like to book?"
    if field == "location":
        locations = [l.get("name") for l in (kb.get("locations") or []) if l.get("name")]
        if locations:
            return "Which location do you prefer? Options: " + ", ".join(locations)
        return "Which location do you prefer?"
    if field == "date":
        return "What date would you like? (e.g., 21 Dec)"
    if field == "time":
        return "What time works for you? (e.g., 10:30 AM)"
    if field == "contact":
        return "What contact should we use? (name and phone/email)"
    return "Please provide " + field + "."

def _kb_summary(kb: dict) -> str:
    services = kb.get("services") or []
    locations = kb.get("locations") or []
    lines = []
    if kb.get("clinic_name"):
        lines.append(f"Clinic: {kb['clinic_name']}")
    if services:
        lines.append("Services:")
        for s in services:
            name = s.get("name") or "service"
            price = s.get("price_sgd")
            duration = s.get("duration_minutes")
            bits = [name]
            if duration:
                bits.append(f"{duration} min")
            if price is not None:
                bits.append(f"SGD {price}")
            lines.append(" - " + " • ".join(bits))
    if locations:
        lines.append("Locations & Hours:")
        for l in locations:
            name = l.get("name") or "location"
            addr = l.get("address") or ""
            hours = l.get("hours") or {}
            lines.append(f" - {name}: {addr}".rstrip())
            if hours:
                lines.append(f"   Mon-Fri: {hours.get('mon_fri', 'n/a')}")
                lines.append(f"   Sat: {hours.get('sat', 'n/a')}")
                lines.append(f"   Sun: {hours.get('sun', 'n/a')}")
    if kb.get("time_policy"):
        lines.append(f"Time policy: {kb['time_policy']}")
    if kb.get("date_policy"):
        lines.append(f"Date policy: {kb['date_policy']}")
    return "\n".join(lines) if lines else "No clinic info available."

def _is_info_request(text: str) -> bool:
    return re.search(r"\b(services|service list|opening hours|hours|locations|price|pricing|clinic info|clinic information)\b", text.lower()) is not None

def _is_booking_related(text: str) -> bool:
    return re.search(r"\b(book|booking|appointment|schedule|reschedule|cancel|change|edit)\b", text.lower()) is not None

def _is_confirm_intent(text: str) -> bool:
    return re.search(r"\b(confirm|confirmed|yes|okay|ok|sure)\b", text.lower()) is not None

def _find_service(name: str, kb: dict) -> str | None:
    name = name.strip().lower()
    for s in kb.get("services") or []:
        n = (s.get("name") or "").strip()
        if n.lower() == name:
            return n
    return None

def _best_fuzzy_match(value: str, options: list[str], threshold: float = 0.78) -> str | None:
    best = None
    best_score = 0.0
    for opt in options:
        score = SequenceMatcher(None, value.lower(), opt.lower()).ratio()
        if score > best_score:
            best_score = score
            best = opt
    if best_score >= threshold:
        return best
    return None

def _extract_service_from_text(text: str, kb: dict) -> str | None:
    t = text.lower()
    services = [s.get("name") for s in (kb.get("services") or []) if s.get("name")]
    for n in services:
        if n and n.lower() in t:
            return n
    return _best_fuzzy_match(text, services)

def _find_location(name: str, kb: dict) -> str | None:
    name = name.strip().lower()
    for l in kb.get("locations") or []:
        n = (l.get("name") or "").strip()
        if n.lower() == name:
            return n
    return None

def _fuzzy_service(value: str, kb: dict) -> str | None:
    services = [s.get("name") for s in (kb.get("services") or []) if s.get("name")]
    return _best_fuzzy_match(value, services)

def _fuzzy_location(value: str, kb: dict) -> str | None:
    locations = [l.get("name") for l in (kb.get("locations") or []) if l.get("name")]
    return _best_fuzzy_match(value, locations)

def _valid_time(value: str) -> bool:
    v = value.strip().lower()
    return re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", v) is not None or re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", v) is not None

def _valid_date(value: str) -> bool:
    v = value.strip().lower()
    return re.search(r"\b\d{4}-\d{2}-\d{2}\b", v) is not None or re.search(r"\b\d{1,2}\s*[a-z]{3,9}\b", v) is not None

def _parse_time_to_minutes(value: str) -> int | None:
    v = value.strip().lower()
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", v)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"\b(\d{1,2})(?::([0-5]\d))?\s*(am|pm)\b", v)
    if m:
        hour = int(m.group(1)) % 12
        minute = int(m.group(2) or 0)
        if m.group(3) == "pm":
            hour += 12
        return hour * 60 + minute
    return None

def _extract_time_text(value: str) -> str | None:
    v = value.strip().lower()
    m = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", v)
    if m:
        return m.group(0)
    m = re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", v)
    if m:
        return m.group(0)
    return None

def _is_time_within_hours(time_value: str, location_name: str, kb: dict) -> bool:
    minutes = _parse_time_to_minutes(time_value)
    if minutes is None:
        return False
    for loc in kb.get("locations") or []:
        if (loc.get("name") or "").strip().lower() == location_name.strip().lower():
            hours = loc.get("hours") or {}
            # Use mon_fri as default window for validation.
            window = hours.get("mon_fri") or ""
            m = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", window)
            if not m:
                return True
            start = int(m.group(1)) * 60 + int(m.group(2))
            end = int(m.group(3)) * 60 + int(m.group(4))
            return start <= minutes <= end
    return True

def _finalize_booking(draft: dict, confirmation_summary: str) -> dict:
    booking = {
        "id": str(uuid4()),
        "booking_type": draft.get("booking_type") or "",
        "details": draft.get("details") or {},
        "status": "booked",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "confirmation_summary": confirmation_summary or ""
    }
    return booking

@app.post("/chat")
def chat(body: ChatIn, x_session_id: str | None = Header(default=None)):
    user_msg = body.message.strip()
    if not user_msg:
        return {"reply": "Please type something."}

    session_id = body.session_id or x_session_id or str(uuid4())
    store = _load_store()
    session = store.get(session_id) or {"draft": _new_draft(), "bookings": [], "history": []}
    kb = _load_kb()

    draft = session.get("draft") or _new_draft()

    # If user mentions a service in free text, capture it (smart inference).
    if not (draft.get("details") or {}).get("service"):
        kb = _load_kb()
        inferred = _extract_service_from_text(user_msg, kb)
        if inferred:
            draft["pending_field"] = "service"
            draft["pending_value"] = inferred
            draft["last_field"] = ""
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": f"Did you want to book **{inferred}**? (yes/no)", "session_id": session_id}

    # Handle per-field confirmation (early)
    if draft.get("pending_field"):
        if re.search(r"\b(yes|confirm|ok|okay|sure)\b", user_msg.lower()):
            field = draft["pending_field"]
            value = draft["pending_value"]
            draft["details"][field] = value
            draft["pending_field"] = ""
            draft["pending_value"] = ""
            draft["updated_at"] = _now_iso()
            draft["missing_fields"] = _missing_fields(draft)
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            # ask next field
            missing = _missing_fields(draft)
            if missing:
                draft["last_field"] = missing[0]
                session["draft"] = draft
                store[session_id] = session
                _save_store(store)
                return {"reply": _question_for(missing[0], _load_kb()), "session_id": session_id}
            # all fields done -> ask final confirmation
            draft["awaiting_confirmation"] = True
            draft["confirmation_summary"] = _format_booking(draft)
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {
                "reply": "Please confirm your booking details (yes/no):\n" + draft["confirmation_summary"],
                "session_id": session_id
            }
        if re.search(r"\b(no|change|edit|wrong)\b", user_msg.lower()):
            field = draft["pending_field"]
            draft["pending_field"] = ""
            draft["pending_value"] = ""
            draft["last_field"] = field
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": _question_for(field, _load_kb()), "session_id": session_id}

    # If the assistant asked for a specific field last turn, treat this user reply as the value.
    last_field = (draft.get("last_field") or "").strip()
    if last_field and not re.search(r"\b(my booking|booking details|booking status|what did i book)\b", user_msg.lower()) and not _is_info_request(user_msg):
        kb = _load_kb()
        value = user_msg.strip()
        # validate + normalize, but don't commit until user confirms
        if last_field == "service":
            match = _find_service(value, kb)
            if not match:
                suggestion = _fuzzy_service(value, kb)
                if suggestion:
                    draft["pending_field"] = "service"
                    draft["pending_value"] = suggestion
                    draft["last_field"] = ""
                    session["draft"] = draft
                    store[session_id] = session
                    _save_store(store)
                    return {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id}
                return {"reply": "Invalid service. Please re-enter a valid service from the list.", "session_id": session_id}
            value = match
        elif last_field == "location":
            match = _find_location(value, kb)
            if not match:
                suggestion = _fuzzy_location(value, kb)
                if suggestion:
                    draft["pending_field"] = "location"
                    draft["pending_value"] = suggestion
                    draft["last_field"] = ""
                    session["draft"] = draft
                    store[session_id] = session
                    _save_store(store)
                    return {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id}
                return {"reply": "Invalid location. Please re-enter a valid location from the list.", "session_id": session_id}
            value = match
        elif last_field == "time":
            time_text = _extract_time_text(value)
            if not time_text:
                return {"reply": "Invalid time format. Please re-enter (e.g., 10:30 AM).", "session_id": session_id}
            loc = (draft.get("details") or {}).get("location", "")
            if loc and not _is_time_within_hours(time_text, loc, kb):
                return {"reply": "That time is outside the location’s operating hours. Please enter a time within hours.", "session_id": session_id}
            value = time_text
        elif last_field == "date":
            if not _valid_date(value):
                return {"reply": "Invalid date format. Please re-enter (e.g., 21 Dec or 2026-02-10).", "session_id": session_id}
        elif last_field == "contact":
            if len(value) < 3:
                return {"reply": "Invalid contact. Please re-enter your name and phone/email.", "session_id": session_id}

        draft["pending_field"] = last_field
        draft["pending_value"] = value
        draft["last_field"] = ""
        draft["updated_at"] = _now_iso()
        session["draft"] = draft
        store[session_id] = session
        _save_store(store)
        return {"reply": f"Got it. Please confirm {last_field}: {value} (yes/no)", "session_id": session_id}

    # Handle confirmation
    if draft.get("awaiting_confirmation"):
        # If user provides a time (e.g., "yes 12pm"), treat it as time edit.
        time_text = _extract_time_text(user_msg)
        if time_text:
            loc = (draft.get("details") or {}).get("location", "")
            kb = _load_kb()
            if loc and not _is_time_within_hours(time_text, loc, kb):
                return {"reply": "That time is outside the location’s operating hours. Please enter a time within hours.", "session_id": session_id}
            draft["details"]["time"] = time_text
            draft["awaiting_confirmation"] = False
            draft["confirmation_summary"] = ""
            draft["updated_at"] = _now_iso()
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": "Got it. Updated the time. Please confirm the booking details again.", "session_id": session_id}

        if re.search(r"\b(yes|confirm|looks good|ok|okay|sure|correct)\b", user_msg.lower()):
            booking = _finalize_booking(draft, draft.get("confirmation_summary") or "")
            session["bookings"].append(booking)
            session["draft"] = _new_draft()
            session["history"].append({"at": _now_iso(), "user": user_msg, "assistant": "Successfully booked."})
            store[session_id] = session
            _save_store(store)
            return {"reply": "Successfully booked.", "session_id": session_id}
        if re.search(r"\b(no|change|edit|not correct|wrong)\b", user_msg.lower()):
            draft["awaiting_confirmation"] = False
            draft["confirmation_summary"] = ""
            draft["updated_at"] = _now_iso()
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": "Okay, tell me what you want to change.", "session_id": session_id}

    # If user explicitly confirms and draft is complete, finalize immediately
    if _is_confirm_intent(user_msg):
        if not _missing_fields(draft):
            booking = _finalize_booking(draft, _format_booking(draft))
            session["bookings"].append(booking)
            session["draft"] = _new_draft()
            session["history"].append({"at": _now_iso(), "user": user_msg, "assistant": "Successfully booked."})
            store[session_id] = session
            _save_store(store)
            return {"reply": "Successfully booked.", "session_id": session_id}
        else:
            missing = _missing_fields(draft)
            draft["last_field"] = missing[0]
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": _question_for(missing[0], _load_kb()), "session_id": session_id}

    # Quick status lookup without calling the model
    if re.search(r"\b(my booking|booking details|booking status|what did i book)\b", user_msg.lower()):
        bookings = session.get("bookings") or []
        if not bookings:
            return {"reply": "No bookings yet. Want to make one?", "session_id": session_id}
        latest = bookings[-1]
        summary = _format_booking(latest)
        return {"reply": summary, "session_id": session_id}

    # Clinic info lookup
    if _is_info_request(user_msg):
        info = _kb_summary(kb)
        return {"reply": info, "session_id": session_id}

    # Free chat: not about booking flow or clinic info
    if not _is_booking_related(user_msg) and not draft.get("last_field") and not draft.get("awaiting_confirmation") and not _is_confirm_intent(user_msg):
        free_prompt = (
            "You are a helpful assistant. Answer the user's question. "
            "If they ask about the clinic or booking data, use the provided JSON.\n"
            "Be concise and clear."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": free_prompt},
                {"role": "user", "content": json.dumps({
                    "user_message": user_msg,
                    "clinic_kb": kb,
                    "current_booking": draft,
                    "bookings_count": len(session.get("bookings") or [])
                })}
            ]
        )
        reply = resp.choices[0].message.content or "Sorry, I don't have that."
        session["history"].append({"at": _now_iso(), "user": user_msg, "assistant": reply})
        store[session_id] = session
        _save_store(store)
        return {"reply": reply, "session_id": session_id}

    # If all required fields are present, ask for confirmation (server-side)
    if not _missing_fields(draft) and not draft.get("awaiting_confirmation"):
        draft["awaiting_confirmation"] = True
        draft["confirmation_summary"] = _format_booking(draft)
        session["draft"] = draft
        store[session_id] = session
        _save_store(store)
        return {
            "reply": "Please confirm your booking details (yes/no):\n" + draft["confirmation_summary"],
            "session_id": session_id
        }

    # If we already have some details, drive the next question server-side to avoid repeats.
    if draft.get("details") and not draft.get("awaiting_confirmation"):
        missing = _missing_fields(draft)
        draft["missing_fields"] = missing
        if missing:
            draft["last_field"] = missing[0]
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return {"reply": _question_for(missing[0], _load_kb()), "session_id": session_id}

    system_prompt = (
        "You are a professional booking assistant for APPOINTMENTS ONLY. "
        "You do NOT handle flights, hotels, restaurants, events, or rentals. "
        "You do NOT actually place bookings; you only collect details and return "
        "a clear confirmation summary.\n\n"
        "You MUST reply with a single JSON object and no extra text.\n"
        "JSON shape:\n"
        "{\n"
        '  "intent": "collect" | "status",\n'
        '  "reply": "assistant message to user",\n'
        '  "booking_type": "string or empty",\n'
        '  "details": { "field": "value", ... },\n'
        '  "missing_fields": ["field1", "field2"],\n'
        '  "is_complete": true | false,\n'
        '  "confirmation_summary": "string"\n'
        "}\n\n"
        "Rules:\n"
        "- If the user asks about their booking, set intent to status and reply with the stored summary request.\n"
        "- Otherwise, set intent to collect.\n"
        "- Start by asking what service they want to book.\n"
        "- Ask for ONLY ONE missing field at a time (one question per turn).\n"
        "- Required fields for appointments:\n"
        "  service, date, time, location, contact\n"
        "- Optional: provider\n"
        "- You MUST only accept services, locations, hours, and pricing from the clinic knowledge base.\n"
        "- If the user asks for something not in the knowledge base, ask them to pick a valid option.\n"
        "- If a time is outside the location hours, ask for a time within hours.\n"
        "- When all required fields are present, set is_complete=true and provide a confirmation_summary.\n"
        "- Your reply should ask the user to confirm the summary.\n"
        "- Be concise, professional, and helpful."
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({
                "user_message": user_msg,
                "current_booking": draft,
                "completed_bookings_count": len(session.get("bookings") or []),
                "recent_history": session.get("history")[-6:],
                "clinic_kb": kb
            })}
        ]
    )
    raw = resp.choices[0].message.content or ""

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {
            "intent": "collect",
            "reply": raw.strip() or "I can help with bookings. What are you trying to book?",
            "booking_type": "",
            "details": {},
            "missing_fields": [],
            "is_complete": False,
            "confirmation_summary": ""
        }

    if parsed.get("intent") == "collect":
        if parsed.get("booking_type"):
            draft["booking_type"] = parsed["booking_type"]
        details = parsed.get("details") or {}
        # Validate model-suggested details before accepting
        kb = _load_kb()
        for k, v in details.items():
            if k == "service":
                match = _find_service(str(v), kb)
                if not match:
                    suggestion = _fuzzy_service(str(v), kb)
                    if suggestion:
                        draft["pending_field"] = "service"
                        draft["pending_value"] = suggestion
                        session["draft"] = draft
                        store[session_id] = session
                        _save_store(store)
                        return {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id}
                    return {"reply": "Invalid service. Please re-enter a valid service from the list.", "session_id": session_id}
                draft["details"][k] = match
            elif k == "location":
                match = _find_location(str(v), kb)
                if not match:
                    suggestion = _fuzzy_location(str(v), kb)
                    if suggestion:
                        draft["pending_field"] = "location"
                        draft["pending_value"] = suggestion
                        session["draft"] = draft
                        store[session_id] = session
                        _save_store(store)
                        return {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id}
                    return {"reply": "Invalid location. Please re-enter a valid location from the list.", "session_id": session_id}
                draft["details"][k] = match
            elif k == "time":
                time_text = _extract_time_text(str(v))
                if not time_text:
                    return {"reply": "Invalid time format. Please re-enter (e.g., 10:30 AM).", "session_id": session_id}
                loc = (draft.get("details") or {}).get("location", "")
                if loc and not _is_time_within_hours(time_text, loc, kb):
                    return {"reply": "That time is outside the location’s operating hours. Please enter a time within hours.", "session_id": session_id}
                draft["details"][k] = time_text
            elif k == "date":
                if not _valid_date(str(v)):
                    return {"reply": "Invalid date format. Please re-enter (e.g., 21 Dec or 2026-02-10).", "session_id": session_id}
                draft["details"][k] = str(v).strip()
            elif k == "contact":
                if len(str(v).strip()) < 3:
                    return {"reply": "Invalid contact. Please re-enter your name and phone/email.", "session_id": session_id}
                draft["details"][k] = str(v).strip()
            else:
                draft["details"][k] = v
        draft["updated_at"] = _now_iso()
        draft["missing_fields"] = parsed.get("missing_fields") or _missing_fields(draft)
        if draft["missing_fields"]:
            draft["last_field"] = draft["missing_fields"][0]

        # If model says complete but required fields are missing, override.
        if parsed.get("is_complete") and not _missing_fields(draft):
            loc = (draft.get("details") or {}).get("location", "")
            time_val = (draft.get("details") or {}).get("time", "")
            if loc and time_val and not _is_time_within_hours(time_val, loc, _load_kb()):
                draft["last_field"] = "time"
                reply = "That time is outside the location’s operating hours. Please enter a time within hours."
            else:
                draft["awaiting_confirmation"] = True
                draft["confirmation_summary"] = parsed.get("confirmation_summary") or ""
                reply = (parsed.get("reply") or "Please confirm the details below.") + "\n" + (
                    draft["confirmation_summary"] or _format_booking(draft)
                )
        else:
            # Server-side fallback if model reply is empty or missing fields exist
            missing = _missing_fields(draft)
            if missing:
                draft["last_field"] = missing[0]
                reply = _question_for(missing[0], _load_kb())
            else:
                reply = parsed.get("reply") or "What would you like to book?"
    else:
        reply = parsed.get("reply") or "Want to make a booking?"

    session["draft"] = draft
    session["history"].append({"at": _now_iso(), "user": user_msg, "assistant": reply})
    store[session_id] = session
    _save_store(store)

    return {"reply": reply, "session_id": session_id}

@app.get("/bookings")
def list_bookings(session_id: str):
    store = _load_store()
    session = store.get(session_id) or {"draft": _new_draft(), "bookings": [], "history": []}
    return {"bookings": session.get("bookings") or []}

@app.delete("/bookings/{booking_id}")
def delete_booking(booking_id: str, session_id: str):
    store = _load_store()
    session = store.get(session_id)
    if not session:
        return {"ok": False, "error": "session not found"}
    bookings = session.get("bookings") or []
    new_bookings = [b for b in bookings if b.get("id") != booking_id]
    if len(new_bookings) == len(bookings):
        return {"ok": False, "error": "booking not found"}
    session["bookings"] = new_bookings
    store[session_id] = session
    _save_store(store)
    return {"ok": True}

@app.post("/history/clear")
def clear_history(session_id: str):
    store = _load_store()
    session = store.get(session_id)
    if not session:
        return {"ok": False, "error": "session not found"}
    session["history"] = []
    store[session_id] = session
    _save_store(store)
    return {"ok": True}

@app.get("/clinic/info")
def clinic_info():
    kb = _load_kb()
    return {"clinic": kb}
