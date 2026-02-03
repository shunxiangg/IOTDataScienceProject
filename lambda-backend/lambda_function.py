import os
import json
import re
from uuid import uuid4
from datetime import datetime, timezone
from difflib import SequenceMatcher
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

STORE_PATH = "/tmp/booking_store.json"

CLINIC_KB = {
    "clinic_name": "BookBot Clinic",
    "services": [
        {"name": "General Consultation", "duration_minutes": 30, "price_sgd": 60},
        {"name": "Dental Cleaning", "duration_minutes": 45, "price_sgd": 120},
        {"name": "Physiotherapy", "duration_minutes": 60, "price_sgd": 150},
        {"name": "Vaccination", "duration_minutes": 15, "price_sgd": 40},
    ],
    "locations": [
        {
            "name": "Raffles Place",
            "address": "1 Raffles Place, Singapore 048616",
            "hours": {"mon_fri": "09:00-18:00", "sat": "09:00-13:00", "sun": "closed"},
        },
        {
            "name": "Orchard",
            "address": "200 Orchard Rd, Singapore 238852",
            "hours": {"mon_fri": "10:00-19:00", "sat": "10:00-14:00", "sun": "closed"},
        },
        {
            "name": "Tampines",
            "address": "10 Tampines Central 1, Singapore 529536",
            "hours": {"mon_fri": "09:00-18:30", "sat": "09:00-13:00", "sun": "closed"},
        },
    ],
    "time_policy": "Appointments are scheduled in 15-minute increments within location hours.",
    "date_policy": "Bookings allowed up to 60 days in advance.",
}

REQUIRED_FIELDS = ["service", "date", "time", "location", "contact"]


def _resp(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Session-Id",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
        },
        "body": json.dumps(body),
    }


def _load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_store(store: dict) -> None:
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=True)


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
        "confirmation_summary": "",
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
            lines.append(" - " + " | ".join(bits))
    if locations:
        lines.append("Locations and Hours:")
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
    return re.search(
        r"\b(services|service list|opening hours|hours|locations|price|pricing|clinic info|clinic information)\b",
        text.lower(),
    ) is not None


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
    return re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", v) is not None or re.search(
        r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", v
    ) is not None


def _valid_date(value: str) -> bool:
    v = value.strip().lower()
    return re.search(r"\b\d{4}-\d{2}-\d{2}\b", v) is not None or re.search(
        r"\b\d{1,2}\s*[a-z]{3,9}\b", v
    ) is not None


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
        "confirmation_summary": confirmation_summary or "",
    }
    return booking


def _handle_chat(event, session_id: str, body: dict):
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return _resp(400, {"error": "message is required"})

    store = _load_store()
    session = store.get(session_id) or {"draft": _new_draft(), "bookings": [], "history": []}
    kb = CLINIC_KB
    draft = session.get("draft") or _new_draft()

    # infer service from free text
    if not (draft.get("details") or {}).get("service"):
        inferred = _extract_service_from_text(user_msg, kb)
        if inferred:
            draft["pending_field"] = "service"
            draft["pending_value"] = inferred
            draft["last_field"] = ""
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return _resp(200, {"reply": f"Did you want to book **{inferred}**? (yes/no)", "session_id": session_id})

    # per-field confirmation
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
            missing = _missing_fields(draft)
            if missing:
                draft["last_field"] = missing[0]
                session["draft"] = draft
                store[session_id] = session
                _save_store(store)
                return _resp(200, {"reply": _question_for(missing[0], kb), "session_id": session_id})
            draft["awaiting_confirmation"] = True
            draft["confirmation_summary"] = _format_booking(draft)
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return _resp(
                200,
                {"reply": "Please confirm your booking details (yes/no):\n" + draft["confirmation_summary"], "session_id": session_id},
            )
        if re.search(r"\b(no|change|edit|wrong)\b", user_msg.lower()):
            field = draft["pending_field"]
            draft["pending_field"] = ""
            draft["pending_value"] = ""
            draft["last_field"] = field
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return _resp(200, {"reply": _question_for(field, kb), "session_id": session_id})

    # last field capture
    last_field = (draft.get("last_field") or "").strip()
    if last_field and not _is_info_request(user_msg):
        value = user_msg.strip()
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
                    return _resp(200, {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id})
                return _resp(200, {"reply": "Invalid service. Please re-enter a valid service from the list.", "session_id": session_id})
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
                    return _resp(200, {"reply": f"Did you mean {suggestion}? (yes/no)", "session_id": session_id})
                return _resp(200, {"reply": "Invalid location. Please re-enter a valid location from the list.", "session_id": session_id})
            value = match
        elif last_field == "time":
            time_text = _extract_time_text(value)
            if not time_text:
                return _resp(200, {"reply": "Invalid time format. Please re-enter (e.g., 10:30 AM).", "session_id": session_id})
            loc = (draft.get("details") or {}).get("location", "")
            if loc and not _is_time_within_hours(time_text, loc, kb):
                return _resp(200, {"reply": "That time is outside the location's operating hours. Please enter a time within hours.", "session_id": session_id})
            value = time_text
        elif last_field == "date":
            if not _valid_date(value):
                return _resp(200, {"reply": "Invalid date format. Please re-enter (e.g., 21 Dec or 2026-02-10).", "session_id": session_id})
        elif last_field == "contact":
            if len(value) < 3:
                return _resp(200, {"reply": "Invalid contact. Please re-enter your name and phone/email.", "session_id": session_id})

        draft["pending_field"] = last_field
        draft["pending_value"] = value
        draft["last_field"] = ""
        draft["updated_at"] = _now_iso()
        session["draft"] = draft
        store[session_id] = session
        _save_store(store)
        return _resp(200, {"reply": f"Got it. Please confirm {last_field}: {value} (yes/no)", "session_id": session_id})

    # status lookup
    if re.search(r"\b(my booking|booking details|booking status|what did i book)\b", user_msg.lower()):
        bookings = session.get("bookings") or []
        if not bookings:
            return _resp(200, {"reply": "No bookings yet. Want to make one?", "session_id": session_id})
        latest = bookings[-1]
        summary = _format_booking(latest)
        return _resp(200, {"reply": summary, "session_id": session_id})

    # clinic info lookup
    if _is_info_request(user_msg):
        info = _kb_summary(kb)
        return _resp(200, {"reply": info, "session_id": session_id})

    # free chat
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
                {"role": "user", "content": json.dumps({"user_message": user_msg, "clinic_kb": kb, "current_booking": draft})},
            ],
        )
        reply = resp.choices[0].message.content or "Sorry, I do not have that."
        session["history"].append({"at": _now_iso(), "user": user_msg, "assistant": reply})
        store[session_id] = session
        _save_store(store)
        return _resp(200, {"reply": reply, "session_id": session_id})

    # final confirmation
    if not _missing_fields(draft) and not draft.get("awaiting_confirmation"):
        draft["awaiting_confirmation"] = True
        draft["confirmation_summary"] = _format_booking(draft)
        session["draft"] = draft
        store[session_id] = session
        _save_store(store)
        return _resp(200, {"reply": "Please confirm your booking details (yes/no):\n" + draft["confirmation_summary"], "session_id": session_id})

    if draft.get("details") and not draft.get("awaiting_confirmation"):
        missing = _missing_fields(draft)
        draft["missing_fields"] = missing
        if missing:
            draft["last_field"] = missing[0]
            session["draft"] = draft
            store[session_id] = session
            _save_store(store)
            return _resp(200, {"reply": _question_for(missing[0], kb), "session_id": session_id})

    return _resp(200, {"reply": "What service would you like to book?", "session_id": session_id})


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("requestContext", {}).get("http", {}).get("path", "")
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    query = event.get("queryStringParameters") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    session_id = query.get("session_id") or headers.get("x-session-id")

    if method == "GET" and path == "/clinic/info":
        return _resp(200, {"clinic": CLINIC_KB})

    if method == "GET" and path == "/bookings":
        if not session_id:
            return _resp(400, {"error": "session_id is required"})
        store = _load_store()
        session = store.get(session_id) or {"draft": _new_draft(), "bookings": [], "history": []}
        return _resp(200, {"bookings": session.get("bookings") or []})

    if path.startswith("/bookings/") and method == "GET":
        if not session_id:
            return _resp(400, {"error": "session_id is required"})
        booking_id = path.split("/bookings/")[1]
        store = _load_store()
        session = store.get(session_id) or {"draft": _new_draft(), "bookings": [], "history": []}
        for b in session.get("bookings") or []:
            if b.get("id") == booking_id:
                return _resp(200, {"booking": b})
        return _resp(404, {"error": "booking not found"})

    if path.startswith("/bookings/") and method == "PATCH":
        if not session_id:
            return _resp(400, {"error": "session_id is required"})
        booking_id = path.split("/bookings/")[1]
        body = event.get("body") or "{}"
        if isinstance(body, str):
            body = json.loads(body)
        store = _load_store()
        session = store.get(session_id)
        if not session:
            return _resp(404, {"error": "session not found"})
        bookings = session.get("bookings") or []
        updates = body.get("details") or {}
        for b in bookings:
            if b.get("id") == booking_id:
                details = b.get("details") or {}
                if "service" in updates and str(updates["service"]).strip():
                    match = _find_service(str(updates["service"]), CLINIC_KB)
                    if not match:
                        return _resp(400, {"error": "invalid service"})
                    details["service"] = match
                if "location" in updates and str(updates["location"]).strip():
                    match = _find_location(str(updates["location"]), CLINIC_KB)
                    if not match:
                        return _resp(400, {"error": "invalid location"})
                    details["location"] = match
                if "date" in updates and str(updates["date"]).strip():
                    if not _valid_date(str(updates["date"])):
                        return _resp(400, {"error": "invalid date"})
                    details["date"] = str(updates["date"]).strip()
                if "time" in updates and str(updates["time"]).strip():
                    time_text = _extract_time_text(str(updates["time"]))
                    if not time_text:
                        return _resp(400, {"error": "invalid time"})
                    loc = details.get("location", "")
                    if loc and not _is_time_within_hours(time_text, loc, CLINIC_KB):
                        return _resp(400, {"error": "time outside hours"})
                    details["time"] = time_text
                if "contact" in updates and str(updates["contact"]).strip():
                    if len(str(updates["contact"]).strip()) < 3:
                        return _resp(400, {"error": "invalid contact"})
                    details["contact"] = str(updates["contact"]).strip()
                b["details"] = details
                b["updated_at"] = _now_iso()
                store[session_id] = session
                _save_store(store)
                return _resp(200, {"ok": True, "booking": b})
        return _resp(404, {"error": "booking not found"})

    if path.startswith("/bookings/") and method == "DELETE":
        if not session_id:
            return _resp(400, {"error": "session_id is required"})
        booking_id = path.split("/bookings/")[1]
        store = _load_store()
        session = store.get(session_id)
        if not session:
            return _resp(404, {"error": "session not found"})
        bookings = session.get("bookings") or []
        new_bookings = [b for b in bookings if b.get("id") != booking_id]
        if len(new_bookings) == len(bookings):
            return _resp(404, {"error": "booking not found"})
        session["bookings"] = new_bookings
        store[session_id] = session
        _save_store(store)
        return _resp(200, {"ok": True})

    if method == "POST" and path == "/history/clear":
        if not session_id:
            return _resp(400, {"error": "session_id is required"})
        store = _load_store()
        session = store.get(session_id)
        if not session:
            return _resp(404, {"error": "session not found"})
        session["history"] = []
        store[session_id] = session
        _save_store(store)
        return _resp(200, {"ok": True})

    if method == "POST" and path == "/chat":
        body = event.get("body") or "{}"
        if isinstance(body, str):
            body = json.loads(body)
        sid = body.get("session_id") or session_id or str(uuid4())
        return _handle_chat(event, sid, body)

    return _resp(404, {"error": "not found"})
