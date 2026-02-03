import { loadStore, saveStore, newDraft } from '../utils.js';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader(
    'Access-Control-Allow-Methods',
    'OPTIONS,POST'
  );
  res.setHeader(
    'Access-Control-Allow-Headers',
    'Content-Type,X-Session-Id'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).json({ ok: true });
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed. Use POST.' });
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

  // Clear history but keep bookings and draft
  session.history = [];
  store[sessionId] = session;
  saveStore(store);

  return res.status(200).json({ ok: true });
}
