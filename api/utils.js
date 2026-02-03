import * as fs from 'fs';

export const STORE_PATH = '/tmp/booking_store.json';

export const CLINIC_KB = {
  clinic_name: 'BookBot Clinic',
  services: [
    { name: 'General Consultation', duration_minutes: 30, price_sgd: 60 },
    { name: 'Dental Cleaning', duration_minutes: 45, price_sgd: 120 },
    { name: 'Physiotherapy', duration_minutes: 60, price_sgd: 150 },
    { name: 'Vaccination', duration_minutes: 15, price_sgd: 40 },
  ],
  locations: [
    {
      name: 'Raffles Place',
      address: '1 Raffles Place, Singapore 048616',
      hours: { mon_fri: '09:00-18:00', sat: '09:00-13:00', sun: 'closed' },
    },
    {
      name: 'Orchard',
      address: '200 Orchard Rd, Singapore 238852',
      hours: { mon_fri: '10:00-19:00', sat: '10:00-14:00', sun: 'closed' },
    },
    {
      name: 'Tampines',
      address: '10 Tampines Central 1, Singapore 529536',
      hours: { mon_fri: '09:00-18:30', sat: '09:00-13:00', sun: 'closed' },
    },
  ],
  time_policy: 'Appointments are scheduled in 15-minute increments within location hours.',
  date_policy: 'Bookings allowed up to 60 days in advance.',
};

export const loadStore = () => {
  try {
    if (fs.existsSync(STORE_PATH)) {
      return JSON.parse(fs.readFileSync(STORE_PATH, 'utf-8'));
    }
  } catch (e) {
    console.error('Error loading store:', e);
  }
  return {};
};

export const saveStore = (store) => {
  try {
    fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2), 'utf-8');
  } catch (e) {
    console.error('Error saving store:', e);
  }
};

export const nowIso = () => new Date().toISOString();

export const newDraft = () => ({
  booking_type: 'appointment',
  details: {},
  status: 'draft',
  created_at: nowIso(),
  updated_at: nowIso(),
  missing_fields: [],
  last_field: '',
  pending_field: '',
  pending_value: '',
  awaiting_confirmation: false,
  confirmation_summary: '',
});

export const findService = (name, kb) => {
  name = name.trim().toLowerCase();
  for (const s of kb.services || []) {
    const n = (s.name || '').trim();
    if (n.toLowerCase() === name) return n;
  }
  return null;
};

export const findLocation = (name, kb) => {
  name = name.trim().toLowerCase();
  for (const l of kb.locations || []) {
    const n = (l.name || '').trim();
    if (n.toLowerCase() === name) return n;
  }
  return null;
};

export const validDate = (value) => {
  const v = value.trim().toLowerCase();
  return (
    /\b\d{4}-\d{2}-\d{2}\b/.test(v) || /\b\d{1,2}\s*[a-z]{3,9}\b/.test(v)
  );
};

export const extractTimeText = (value) => {
  const v = value.trim().toLowerCase();
  let m = v.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/);
  if (m) return m[0];
  m = v.match(/\b\d{1,2}(:\d{2})?\s*(am|pm)\b/);
  if (m) return m[0];
  return null;
};

export const parseTimeToMinutes = (value) => {
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

export const isTimeWithinHours = (timeValue, locationName, kb) => {
  const minutes = parseTimeToMinutes(timeValue);
  if (minutes === null) return false;
  for (const loc of kb.locations || []) {
    if ((loc.name || '').trim().toLowerCase() === locationName.trim().toLowerCase()) {
      const hours = loc.hours || {};
      const window = hours.mon_fri || '';
      const m = window.match(/(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/);
      if (!m) return true;
      const start = parseInt(m[1]) * 60 + parseInt(m[2]);
      const end = parseInt(m[3]) * 60 + parseInt(m[4]);
      return start <= minutes && minutes <= end;
    }
  }
  return true;
};
