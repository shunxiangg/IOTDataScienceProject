import { loadStore, newDraft } from './utils.js';

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

  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed. Use GET.' });
  }

  const sessionId = req.query.session_id || req.headers['x-session-id'];
  if (!sessionId) {
    return res.status(400).json({ error: 'session_id is required' });
  }

  const store = loadStore();
  const session = store[sessionId] || {
    draft: newDraft(),
    bookings: [],
    history: [],
  };

  return res.status(200).json({ bookings: session.bookings || [] });
}
