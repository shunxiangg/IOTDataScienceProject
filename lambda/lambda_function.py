import json
import datetime

BUSINESS_START = 10
BUSINESS_END = 17  # closes at 5pm
SLOT_MINUTES = [0, 30]

APPT_TYPES = {
    "cleaning": 30,
    "root canal": 60,
    "whitening": 30
}

def _get_slot(event, name):
    slots = event["sessionState"]["intent"].get("slots") or {}
    slot = slots.get(name)
    if not slot or not slot.get("value"):
        return None
    return slot["value"].get("interpretedValue")

def _set_slot(event, name, value_or_none):
    slots = event["sessionState"]["intent"].setdefault("slots", {})
    if value_or_none is None:
        slots[name] = None
    else:
        slots[name] = {"value": {"originalValue": value_or_none, "interpretedValue": value_or_none}}

def _msg(text):
    return {"contentType": "PlainText", "content": text}

def elicit_slot(event, slot_to_elicit, message):
    return {
        "sessionState": {
            "sessionAttributes": event["sessionState"].get("sessionAttributes", {}),
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot_to_elicit},
            "intent": event["sessionState"]["intent"]
        },
        "messages": [_msg(message)]
    }

def confirm_intent(event, message):
    return {
        "sessionState": {
            "sessionAttributes": event["sessionState"].get("sessionAttributes", {}),
            "dialogAction": {"type": "ConfirmIntent"},
            "intent": event["sessionState"]["intent"]
        },
        "messages": [_msg(message)]
    }

def close(event, state, message):
    event["sessionState"]["intent"]["state"] = state
    return {
        "sessionState": {
            "sessionAttributes": event["sessionState"].get("sessionAttributes", {}),
            "dialogAction": {"type": "Close"},
            "intent": event["sessionState"]["intent"]
        },
        "messages": [_msg(message)]
    }

def delegate(event):
    return {
        "sessionState": {
            "sessionAttributes": event["sessionState"].get("sessionAttributes", {}),
            "dialogAction": {"type": "Delegate"},
            "intent": event["sessionState"]["intent"]
        }
    }

def _is_weekday(date_obj):
    return date_obj.weekday() < 5

def _parse_date(date_str):
    # Lex usually gives YYYY-MM-DD
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

def _valid_time(t):
    # Expect HH:MM
    try:
        hh, mm = t.split(":")
        hh = int(hh); mm = int(mm)
        if mm not in SLOT_MINUTES: return False
        if hh < BUSINESS_START or hh >= BUSINESS_END: return False
        return True
    except:
        return False

def _availabilities():
    # Simple fixed slots (you can later connect to DB)
    return ["10:00","10:30","11:00","11:30","14:00","14:30","15:00","15:30","16:00","16:30"]

def _duration(appt_type):
    if not appt_type: return None
    return APPT_TYPES.get(appt_type.lower())

def handler_dialog(event):
    appt_type = _get_slot(event, "AppointmentType")
    date_str = _get_slot(event, "Date")
    time_str = _get_slot(event, "Time")

    # Validate appointment type
    if appt_type and _duration(appt_type) is None:
        _set_slot(event, "AppointmentType", None)
        return elicit_slot(event, "AppointmentType", "I can book: cleaning, root canal, or whitening. Which one?")

    if not appt_type:
        return elicit_slot(event, "AppointmentType", "What type of appointment do you want? (cleaning / root canal / whitening)")

    # Validate date
    if date_str:
        try:
            d = _parse_date(date_str)
            today = datetime.date.today()
            if d <= today:
                _set_slot(event, "Date", None)
                return elicit_slot(event, "Date", "Appointments must be at least 1 day in advance. What date works?")
            if not _is_weekday(d):
                _set_slot(event, "Date", None)
                return elicit_slot(event, "Date", "We’re closed on weekends. Please choose a weekday (YYYY-MM-DD).")
        except:
            _set_slot(event, "Date", None)
            return elicit_slot(event, "Date", "Please use date format YYYY-MM-DD.")

    if not date_str:
        return elicit_slot(event, "Date", f"When would you like your {appt_type}? (YYYY-MM-DD)")

    # Validate time
    if time_str and not _valid_time(time_str):
        _set_slot(event, "Time", None)
        return elicit_slot(event, "Time", "Please choose a time between 10:00 and 16:30 (every 30 mins).")

    if not time_str:
        slots = _availabilities()
        sample = ", ".join(slots[:5])
        return elicit_slot(event, "Time", f"What time works? Example slots: {sample}")

    # Everything collected → confirm
    return confirm_intent(event, f"Confirm: {appt_type} on {date_str} at {time_str}? (yes/no)")

def handler_fulfillment(event):
    appt_type = _get_slot(event, "AppointmentType")
    date_str = _get_slot(event, "Date")
    time_str = _get_slot(event, "Time")
    return close(event, "Fulfilled", f"Booked ✅ {appt_type} on {date_str} at {time_str}. Please arrive 10 minutes early.")

def lambda_handler(event, context):
    source = event.get("invocationSource")

    # Lex V2 uses: DialogCodeHook or FulfillmentCodeHook
    if source == "DialogCodeHook":
        return handler_dialog(event)

    if source == "FulfillmentCodeHook":
        return handler_fulfillment(event)

    return delegate(event)
