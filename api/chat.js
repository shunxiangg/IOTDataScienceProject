import { OpenAI } from 'openai';
import { v4 as uuidv4 } from 'uuid';
import {
  CLINIC_KB,
  loadStore,
  saveStore,
  nowIso,
  newDraft,
  findService,
  findLocation,
  validDate,
  extractTimeText,
  isTimeWithinHours,
} from './utils.js';

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const REQUIRED_FIELDS = ['service', 'date', 'time', 'location', 'contact'];

const formatBooking = (booking) => {
  if (!booking) return 'No booking found yet.';
  const lines = [];
  const btype = booking.booking_type || 'unknown';
  lines.push(`**Booking type:** ${btype}`);
  const details = booking.details || {};
  for (const [k, v] of Object.entries(details)) {
    if (v) lines.push(`**${k}:** ${v}`);
  }
  if (booking.status) lines.push(`**status:** ${booking.status}`);
  return lines.join('\n');
};


const missingFields = (draft) => {
  const details = draft.details || {};
  return REQUIRED_FIELDS.filter((f) => !String(details[f] || '').trim());
};

const questionFor = (field, kb) => {
  if (field === 'service') {
    const services = (kb.services || []).map((s) => s.name).filter(Boolean);
    if (services.length)
      return 'What service would you like to book? Options: ' + services.join(', ');
    return 'What service would you like to book?';
  }
  if (field === 'location') {
    const locations = (kb.locations || []).map((l) => l.name).filter(Boolean);
    if (locations.length)
      return 'Which location do you prefer? Options: ' + locations.join(', ');
    return 'Which location do you prefer?';
  }
  if (field === 'date') return 'What date would you like? (e.g., 21 Dec)';
  if (field === 'time') return 'What time works for you? (e.g., 10:30 AM)';
  if (field === 'contact')
    return 'What contact should we use? (name and phone/email)';
  return 'Please provide ' + field + '.';
};

const kbSummary = (kb) => {
  const services = kb.services || [];
  const locations = kb.locations || [];
  const lines = [];
  if (kb.clinic_name) lines.push(`Clinic: ${kb.clinic_name}`);
  if (services.length) {
    lines.push('Services:');
    for (const s of services) {
      const name = s.name || 'service';
      const price = s.price_sgd;
      const duration = s.duration_minutes;
      const bits = [name];
      if (duration) bits.push(`${duration} min`);
      if (price !== undefined) bits.push(`SGD ${price}`);
      lines.push(' - ' + bits.join(' | '));
    }
  }
  if (locations.length) {
    lines.push('Locations and Hours:');
    for (const l of locations) {
      const name = l.name || 'location';
      const addr = l.address || '';
      const hours = l.hours || {};
      lines.push(` - ${name}: ${addr}`);
      if (Object.keys(hours).length) {
        lines.push(`   Mon-Fri: ${hours.mon_fri || 'n/a'}`);
        lines.push(`   Sat: ${hours.sat || 'n/a'}`);
        lines.push(`   Sun: ${hours.sun || 'n/a'}`);
      }
    }
  }
  if (kb.time_policy) lines.push(`Time policy: ${kb.time_policy}`);
  if (kb.date_policy) lines.push(`Date policy: ${kb.date_policy}`);
  return lines.length ? lines.join('\n') : 'No clinic info available.';
};

const isInfoRequest = (text) =>
  /\b(services|service list|opening hours|hours|locations|price|pricing|clinic info|clinic information)\b/i.test(text);

const isBookingRelated = (text) =>
  /\b(book|booking|appointment|schedule|reschedule|cancel|change|edit)\b/i.test(text);

const isConfirmIntent = (text) =>
  /\b(confirm|confirmed|yes|okay|ok|sure)\b/i.test(text);


const sequenceMatcherRatio = (s1, s2) => {
  let matches = 0;
  for (let i = 0; i < Math.min(s1.length, s2.length); i++) {
    if (s1[i] === s2[i]) matches++;
  }
  return matches / Math.max(s1.length, s2.length);
};

const bestFuzzyMatch = (value, options, threshold = 0.78) => {
  let best = null;
  let bestScore = 0.0;
  for (const opt of options) {
    const score = sequenceMatcherRatio(
      value.toLowerCase(),
      opt.toLowerCase()
    );
    if (score > bestScore) {
      bestScore = score;
      best = opt;
    }
  }
  return bestScore >= threshold ? best : null;
};

const extractServiceFromText = (text, kb) => {
  const t = text.toLowerCase();
  const services = (kb.services || [])
    .map((s) => s.name)
    .filter(Boolean);
  for (const n of services) {
    if (n && n.toLowerCase().includes(t)) return n;
  }
  return bestFuzzyMatch(text, services);
};


const fuzzyService = (value, kb) => {
  const services = (kb.services || [])
    .map((s) => s.name)
    .filter(Boolean);
  return bestFuzzyMatch(value, services);
};

const fuzzyLocation = (value, kb) => {
  const locations = (kb.locations || [])
    .map((l) => l.name)
    .filter(Boolean);
  return bestFuzzyMatch(value, locations);
};

const validTime = (value) => {
  const v = value.trim().toLowerCase();
  return (
    /\b([01]?\d|2[0-3]):[0-5]\d\b/.test(v) ||
    /\b\d{1,2}(:\d{2})?\s*(am|pm)\b/.test(v)
  );
};

const parseTimeToMinutes = (value) => {
  const v = value.trim().toLowerCase();
  let m = v.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (m) return parseInt(m[1]) * 60 + parseInt(m[2]);
  m = v.match(/\b(\d{1,2})(?::([0-5]\d))?\s*(am|pm)\b/);
  if (m) {
    let hour = parseInt(m[1]) % 12;
    const minute = parseInt(m[2] || 0);
    if (m[3] === 'pm') hour += 12;
    return hour * 60 + minute;
  }
  return null;
};

const finalizeBooking = (draft, confirmationSummary) => ({
  id: uuidv4(),
  booking_type: draft.booking_type || '',
  details: draft.details || {},
  status: 'booked',
  created_at: nowIso(),
  updated_at: nowIso(),
  confirmation_summary: confirmationSummary || '',
});

const handleChat = (sessionId, body) => {
  const userMsg = (body.message || '').trim();
  if (!userMsg) return { status: 400, reply: 'message is required' };

  const store = loadStore();
  let session = store[sessionId] || {
    draft: newDraft(),
    bookings: [],
    history: [],
  };
  const kb = CLINIC_KB;
  let draft = session.draft || newDraft();

  // Infer service from free text
  if (!(draft.details || {}).service) {
    const inferred = extractServiceFromText(userMsg, kb);
    if (inferred) {
      draft.pending_field = 'service';
      draft.pending_value = inferred;
      draft.last_field = '';
      session.draft = draft;
      store[sessionId] = session;
      saveStore(store);
      return {
        status: 200,
        reply: `Did you want to book **${inferred}**? (yes/no)`,
        sessionId,
      };
    }
  }

  // Per-field confirmation
  if (draft.pending_field) {
    if (/\b(yes|confirm|ok|okay|sure)\b/i.test(userMsg)) {
      const field = draft.pending_field;
      const value = draft.pending_value;
      draft.details[field] = value;
      draft.pending_field = '';
      draft.pending_value = '';
      draft.updated_at = nowIso();
      draft.missing_fields = missingFields(draft);
      session.draft = draft;
      store[sessionId] = session;
      saveStore(store);
      const missing = missingFields(draft);
      if (missing.length) {
        draft.last_field = missing[0];
        session.draft = draft;
        store[sessionId] = session;
        saveStore(store);
        return {
          status: 200,
          reply: questionFor(missing[0], kb),
          sessionId,
        };
      }
      draft.awaiting_confirmation = true;
      draft.confirmation_summary = formatBooking(draft);
      session.draft = draft;
      store[sessionId] = session;
      saveStore(store);
      return {
        status: 200,
        reply:
          'Please confirm your booking details (yes/no):\n' +
          draft.confirmation_summary,
        sessionId,
      };
    }
    if (/\b(no|change|edit|wrong)\b/i.test(userMsg)) {
      const field = draft.pending_field;
      draft.pending_field = '';
      draft.pending_value = '';
      draft.last_field = field;
      session.draft = draft;
      store[sessionId] = session;
      saveStore(store);
      return {
        status: 200,
        reply: questionFor(field, kb),
        sessionId,
      };
    }
  }

  // Last field capture
  const lastField = (draft.last_field || '').trim();
  if (lastField && !isInfoRequest(userMsg)) {
    let value = userMsg.trim();
    if (lastField === 'service') {
      const match = findService(value, kb);
      if (!match) {
        const suggestion = fuzzyService(value, kb);
        if (suggestion) {
          draft.pending_field = 'service';
          draft.pending_value = suggestion;
          draft.last_field = '';
          session.draft = draft;
          store[sessionId] = session;
          saveStore(store);
          return {
            status: 200,
            reply: `Did you mean ${suggestion}? (yes/no)`,
            sessionId,
          };
        }
        return {
          status: 200,
          reply:
            'Invalid service. Please re-enter a valid service from the list.',
          sessionId,
        };
      }
      value = match;
    } else if (lastField === 'location') {
      const match = findLocation(value, kb);
      if (!match) {
        const suggestion = fuzzyLocation(value, kb);
        if (suggestion) {
          draft.pending_field = 'location';
          draft.pending_value = suggestion;
          draft.last_field = '';
          session.draft = draft;
          store[sessionId] = session;
          saveStore(store);
          return {
            status: 200,
            reply: `Did you mean ${suggestion}? (yes/no)`,
            sessionId,
          };
        }
        return {
          status: 200,
          reply:
            'Invalid location. Please re-enter a valid location from the list.',
          sessionId,
        };
      }
      value = match;
    } else if (lastField === 'time') {
      const timeText = extractTimeText(value);
      if (!timeText) {
        return {
          status: 200,
          reply:
            'Invalid time format. Please re-enter (e.g., 10:30 AM).',
          sessionId,
        };
      }
      const loc = (draft.details || {}).location || '';
      if (loc && !isTimeWithinHours(timeText, loc, kb)) {
        return {
          status: 200,
          reply:
            "That time is outside the location's operating hours. Please enter a time within hours.",
          sessionId,
        };
      }
      value = timeText;
    } else if (lastField === 'date') {
      if (!validDate(value)) {
        return {
          status: 200,
          reply:
            'Invalid date format. Please re-enter (e.g., 21 Dec or 2026-02-10).',
          sessionId,
        };
      }
    } else if (lastField === 'contact') {
      if (value.length < 3) {
        return {
          status: 200,
          reply:
            'Invalid contact. Please re-enter your name and phone/email.',
          sessionId,
        };
      }
    }

    draft.pending_field = lastField;
    draft.pending_value = value;
    draft.last_field = '';
    draft.updated_at = nowIso();
    session.draft = draft;
    store[sessionId] = session;
    saveStore(store);
    return {
      status: 200,
      reply: `Got it. Please confirm ${lastField}: ${value} (yes/no)`,
      sessionId,
    };
  }

  // Status lookup
  if (
    /\b(my booking|booking details|booking status|what did i book)\b/i.test(
      userMsg
    )
  ) {
    const bookings = session.bookings || [];
    if (!bookings.length) {
      return {
        status: 200,
        reply: 'No bookings yet. Want to make one?',
        sessionId,
      };
    }
    const latest = bookings[bookings.length - 1];
    const summary = formatBooking(latest);
    return {
      status: 200,
      reply: summary,
      sessionId,
    };
  }

  // Clinic info lookup
  if (isInfoRequest(userMsg)) {
    const info = kbSummary(kb);
    return {
      status: 200,
      reply: info,
      sessionId,
    };
  }

  // Free chat
  if (
    !isBookingRelated(userMsg) &&
    !draft.last_field &&
    !draft.awaiting_confirmation &&
    !isConfirmIntent(userMsg)
  ) {
    const freePrompt =
      'You are a helpful assistant. Answer the user\'s question. ' +
      'If they ask about the clinic or booking data, use the provided JSON.\n' +
      'Be concise and clear.';
    return client.chat.completions
      .create({
        model: 'gpt-4o-mini',
        temperature: 0.3,
        messages: [
          { role: 'system', content: freePrompt },
          {
            role: 'user',
            content: JSON.stringify({
              user_message: userMsg,
              clinic_kb: kb,
              current_booking: draft,
            }),
          },
        ],
      })
      .then((resp) => {
        const reply = resp.choices[0].message.content || 'Sorry, I do not have that.';
        session.history.push({
          at: nowIso(),
          user: userMsg,
          assistant: reply,
        });
        store[sessionId] = session;
        saveStore(store);
        return {
          status: 200,
          reply,
          sessionId,
        };
      });
  }

  // Final confirmation
  if (!missingFields(draft).length && !draft.awaiting_confirmation) {
    draft.awaiting_confirmation = true;
    draft.confirmation_summary = formatBooking(draft);
    session.draft = draft;
    store[sessionId] = session;
    saveStore(store);
    return {
      status: 200,
      reply:
        'Please confirm your booking details (yes/no):\n' +
        draft.confirmation_summary,
      sessionId,
    };
  }

  if (draft.details && !draft.awaiting_confirmation) {
    const missing = missingFields(draft);
    draft.missing_fields = missing;
    if (missing.length) {
      draft.last_field = missing[0];
      session.draft = draft;
      store[sessionId] = session;
      saveStore(store);
      return {
        status: 200,
        reply: questionFor(missing[0], kb),
        sessionId,
      };
    }
  }

  return {
    status: 200,
    reply: 'What service would you like to book?',
    sessionId,
  };
};

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader(
    'Access-Control-Allow-Methods',
    'OPTIONS,GET,POST,PATCH,DELETE'
  );
  res.setHeader(
    'Access-Control-Allow-Headers',
    'Content-Type,X-Session-Id'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).json({ ok: true });
  }

  try {
    const sessionId = req.query.session_id || req.headers['x-session-id'] || uuidv4();

    // For Vercel: api/chat.js handles ALL requests to /api/chat
    // So we just handle POST for chat
    if (req.method === 'POST') {
      if (!req.body || !req.body.message) {
        return res.status(400).json({ error: 'Missing message field' });
      }
      const sid = req.body.session_id || sessionId;
      const result = await handleChat(sid, req.body);
      return res.status(result.status).json({
        reply: result.reply,
        session_id: result.sessionId,
      });
    }

    return res.status(405).json({ error: 'Method not allowed. Use POST.' });
  } catch (error) {
    console.error('Chat handler error:', error);
    return res.status(500).json({ 
      error: 'Internal server error',
      message: error.message 
    });
  }
}
