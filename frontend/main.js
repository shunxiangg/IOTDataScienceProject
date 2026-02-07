// Resolve API root once and keep session handling consistent.
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function resolveApiRoot() {
  const host = window.location.hostname.replace(/^\[|\]$/g, "");
  const port = window.location.port;
  if (window.location.protocol === "file:" || LOCAL_HOSTS.has(host) || port === "5500") {
    return "http://127.0.0.1:8000";
  }

  const params = new URLSearchParams(window.location.search);
  const override = params.get("api") || localStorage.getItem("API_ROOT");
  if (override && /^https?:\/\//i.test(override)) {
    return override.replace(/\/$/, "");
  }

  if (host.includes("github.io")) {
    return "https://iot-data-science-project-sxsx.vercel.app/api";
  }
  return "/api";
}

const API_ROOT = resolveApiRoot();

function apiUrl(path) {
  return `${API_ROOT}${path}`;
}

function showApiBanner() {
  const banner = document.createElement("div");
  banner.textContent = `API: ${API_ROOT}`;
  banner.style.position = "fixed";
  banner.style.bottom = "12px";
  banner.style.right = "12px";
  banner.style.zIndex = "9999";
  banner.style.padding = "6px 10px";
  banner.style.fontSize = "12px";
  banner.style.borderRadius = "6px";
  banner.style.background = "rgba(15, 15, 15, 0.8)";
  banner.style.color = "#fff";
  banner.style.fontFamily = "monospace";
  banner.style.boxShadow = "0 4px 12px rgba(0,0,0,0.25)";
  document.body.appendChild(banner);
}

const chat = document.getElementById("chat");
const input = document.getElementById("msg");
const btn = document.getElementById("sendBtn");
const bookingList = document.getElementById("bookingList");
const refreshBtn = document.getElementById("refreshBookings");
const clearHistoryBtn = document.getElementById("clearHistory");
const modal = document.getElementById("bookingModal");
const closeModalBtn = document.getElementById("closeModal");
const saveBookingBtn = document.getElementById("saveBooking");
const modalError = document.getElementById("modalError");
const editService = document.getElementById("editService");
const editDate = document.getElementById("editDate");
const editTime = document.getElementById("editTime");
const editLocation = document.getElementById("editLocation");
const editContact = document.getElementById("editContact");
let activeBookingId = null;

const SERVICE_CATALOG = [
  { name: "General Consultation", duration_minutes: 30, price_sgd: 60 },
  { name: "Dental Cleaning", duration_minutes: 45, price_sgd: 120 },
  { name: "Physiotherapy", duration_minutes: 60, price_sgd: 150 },
  { name: "Vaccination", duration_minutes: 15, price_sgd: 40 }
];

function formatServiceList(services) {
  return services.map((s) => {
    const bits = [s.name];
    if (s.duration_minutes) bits.push(`${s.duration_minutes} min`);
    if (s.price_sgd != null) bits.push(`SGD ${s.price_sgd}`);
    return bits.join(" | ");
  });
}

function addMsg(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + (who === "You" ? "you" : "bot");
  const rendered = renderText(text);
  div.innerHTML = `<b>${who}:</b> ${rendered}`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(s) {
  return s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

function renderText(text) {
  const escaped = escapeHtml(text);
  const bolded = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  return bolded.replace(/\*\*/g, "");
}

const SESSION_KEY = "session_id";

function getSessionId() {
  return localStorage.getItem(SESSION_KEY) || "";
}

function setSessionId(id) {
  if (id) localStorage.setItem(SESSION_KEY, id);
}

function sessionHeaders() {
  const sessionId = getSessionId();
  return sessionId ? { "X-Session-Id": sessionId } : {};
}

function withSession(url) {
  const sessionId = getSessionId();
  if (!sessionId) return url;
  const u = new URL(url, window.location.origin);
  u.searchParams.set("session_id", sessionId);
  return u.toString();
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const errorText = await res.text();
    console.error("API Error:", res.status, errorText);
    throw new Error(`API returned ${res.status}: ${errorText}`);
  }
  return res.json();
}

async function sendToBot(message) {
  const sessionId = getSessionId();
  const payload = { message };
  if (sessionId) payload.session_id = sessionId;

  const data = await fetchJson(apiUrl("/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...sessionHeaders()
    },
    body: JSON.stringify(payload)
  });
  if (data.session_id) setSessionId(data.session_id);
  return data.reply || "(no reply)";
}

async function fetchBookings() {
  const sessionId = getSessionId();
  if (!sessionId) {
    bookingList.innerHTML = "<div class=\"booking-meta\">No session yet.</div>";
    return;
  }
  const data = await fetchJson(withSession(apiUrl("/bookings")), {
    headers: { ...sessionHeaders() }
  });
  renderBookings(data.bookings || []);
}

function renderBookings(bookings) {
  if (!bookings.length) {
    bookingList.innerHTML = "<div class=\"booking-meta\">No bookings yet.</div>";
    return;
  }
  bookingList.innerHTML = bookings.map((b) => {
    const title = b.booking_type || "unknown";
    const detailKeys = Object.keys(b.details || {});
    const detailPreview = detailKeys.slice(0, 2).map((k) => `${k}: ${b.details[k]}`).join(" | ");
    return `
      <div class="booking-card" data-open="${b.id}">
        <div class="booking-title">${escapeHtml(title)}</div>
        <div class="booking-meta">${escapeHtml(detailPreview || "No details")}</div>
        <div class="booking-actions">
          <button class="ghost" data-open="${b.id}">View/Edit</button>
          <button class="danger" data-delete="${b.id}">Delete</button>
        </div>
      </div>
    `;
  }).join("");
}

bookingList.addEventListener("click", async (e) => {
  const deleteBtn = e.target.closest("[data-delete]");
  if (deleteBtn) {
    const id = deleteBtn.getAttribute("data-delete");
    await deleteBooking(id);
    await fetchBookings();
    return;
  }
  const openBtn = e.target.closest("[data-open]");
  if (openBtn) {
    const id = openBtn.getAttribute("data-open");
    await openBooking(id);
  }
});

async function deleteBooking(id) {
  const sessionId = getSessionId();
  if (!sessionId) return;
  await fetchJson(withSession(apiUrl(`/bookings/${id}`)), {
    method: "DELETE",
    headers: { ...sessionHeaders() }
  });
}

async function openBooking(id) {
  const sessionId = getSessionId();
  if (!sessionId) {
    modalError.textContent = "Missing session. Try sending a message first.";
    modal.classList.remove("hidden");
    return;
  }
  const data = await fetchJson(withSession(apiUrl(`/bookings/${id}`)), {
    headers: { ...sessionHeaders() }
  });
  if (!data.booking) {
    modalError.textContent = data.error || "Booking not found.";
    modal.classList.remove("hidden");
    return;
  }
  activeBookingId = id;
  const details = data.booking.details || {};
  editService.value = details.service || "";
  editDate.value = details.date || "";
  editTime.value = details.time || "";
  editLocation.value = details.location || "";
  editContact.value = details.contact || "";
  modalError.textContent = "";
  modal.classList.remove("hidden");
}

async function saveBooking() {
  if (!activeBookingId) return;
  const sessionId = getSessionId();
  const details = {};
  const service = editService.value.trim();
  const date = editDate.value.trim();
  const time = editTime.value.trim();
  const location = editLocation.value.trim();
  const contact = editContact.value.trim();
  if (service) details.service = service;
  if (date) details.date = date;
  if (time) details.time = time;
  if (location) details.location = location;
  if (contact) details.contact = contact;

  const payload = { details };
  const data = await fetchJson(withSession(apiUrl(`/bookings/${activeBookingId}`)), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...sessionHeaders() },
    body: JSON.stringify(payload)
  });
  if (!data.ok) {
    modalError.textContent = data.error || "Failed to update booking.";
    return;
  }
  modal.classList.add("hidden");
  await fetchBookings();
}

async function clearHistory() {
  const sessionId = getSessionId();
  if (!sessionId) return;
  await fetchJson(withSession(apiUrl("/history/clear")), {
    method: "POST",
    headers: { ...sessionHeaders() }
  });
  chat.innerHTML = "";
  addMsg("Bot", "Chat history cleared. Happy now?");
}

function showAvailableServices() {
  if (!SERVICE_CATALOG.length) return;
  const services = formatServiceList(SERVICE_CATALOG);
  addMsg("Bot", "Services available:\n- " + services.join("\n- "));
}

async function onSend() {
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  addMsg("You", text);
  addMsg("Bot", "Typing...");

  const typing = chat.lastChild;

  try {
    const reply = await sendToBot(text);
    typing.remove();
    addMsg("Bot", reply);
    await fetchBookings();
  } catch (e) {
    typing.remove();
    addMsg("Bot", "Error: " + e.message);
    console.error(e);
  }
}

btn.addEventListener("click", onSend);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") onSend(); });
refreshBtn.addEventListener("click", fetchBookings);
clearHistoryBtn.addEventListener("click", clearHistory);
closeModalBtn.addEventListener("click", () => modal.classList.add("hidden"));
saveBookingBtn.addEventListener("click", saveBooking);

addMsg("Bot", "Hi, I'm BookBot. Here are the available services:");
showAvailableServices();
showApiBanner();
fetchBookings();

