import { loadStore, saveStore, CLINIC_KB, nowIso, findService, findLocation, validDate, extractTimeText, isTimeWithinHours } from '../utils.js';

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

  // Extract booking ID from URL path
  // For api/bookings/[id].js, Vercel makes the id available via req.query.id
  // But we need to handle it from the actual request URL
  let bookingId;
  if (req.url) {
    // Parse from req.url if available
    try {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
      const pathParts = url.pathname.split('/').filter(Boolean);
      // pathParts will be ['api', 'bookings', '{id}']
      bookingId = pathParts[pathParts.length - 1];
    } catch (e) {
      // Fallback: try to extract from query or use a default pattern
      bookingId = req.query.id;
    }
  } else {
    // Fallback to query parameter
    bookingId = req.query.id;
  }

  if (!bookingId || bookingId === 'bookings') {
    return res.status(400).json({ error: 'booking id is required' });
  }

  const sessionId = req.query.session_id || req.headers['x-session-id'];
  if (!sessionId) {
    return res.status(400).json({ error: 'session_id is required' });
  }

  const store = loadStore();
  const session = store[sessionId];
  if (!session) {
    return res.status(404).json({ error: 'session not found' });
  }

  const bookings = session.bookings || [];
  const booking = bookings.find((b) => b.id === bookingId);

  if (req.method === 'GET') {
    if (!booking) {
      return res.status(404).json({ error: 'booking not found' });
    }
    return res.status(200).json({ booking });
  }

  if (req.method === 'DELETE') {
    const newBookings = bookings.filter((b) => b.id !== bookingId);
    if (newBookings.length === bookings.length) {
      return res.status(404).json({ error: 'booking not found' });
    }
    session.bookings = newBookings;
    store[sessionId] = session;
    saveStore(store);
    return res.status(200).json({ ok: true });
  }

  if (req.method === 'PATCH') {
    if (!booking) {
      return res.status(404).json({ error: 'booking not found' });
    }

    const updates = req.body.details || {};
    const details = booking.details || {};

    // Validate and update service
    if ('service' in updates && String(updates.service).trim()) {
      const match = findService(String(updates.service), CLINIC_KB);
      if (!match) {
        return res.status(400).json({ error: 'invalid service' });
      }
      details.service = match;
    }

    // Validate and update location
    if ('location' in updates && String(updates.location).trim()) {
      const match = findLocation(String(updates.location), CLINIC_KB);
      if (!match) {
        return res.status(400).json({ error: 'invalid location' });
      }
      details.location = match;
    }

    // Validate and update date
    if ('date' in updates && String(updates.date).trim()) {
      if (!validDate(String(updates.date))) {
        return res.status(400).json({ error: 'invalid date' });
      }
      details.date = String(updates.date).trim();
    }

    // Validate and update time
    if ('time' in updates && String(updates.time).trim()) {
      const timeText = extractTimeText(String(updates.time));
      if (!timeText) {
        return res.status(400).json({ error: 'invalid time' });
      }
      const loc = details.location || '';
      if (loc && !isTimeWithinHours(timeText, loc, CLINIC_KB)) {
        return res.status(400).json({ error: 'time outside hours' });
      }
      details.time = timeText;
    }

    // Validate and update contact
    if ('contact' in updates && String(updates.contact).trim()) {
      if (String(updates.contact).trim().length < 3) {
        return res.status(400).json({ error: 'invalid contact' });
      }
      details.contact = String(updates.contact).trim();
    }

    booking.details = details;
    booking.updated_at = nowIso();
    store[sessionId] = session;
    saveStore(store);

    return res.status(200).json({ ok: true, booking });
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
