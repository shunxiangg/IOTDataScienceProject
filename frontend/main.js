// Auto-detect: Use /api/chat for Vercel, or external API for GitHub Pages
const API_URL = window.location.hostname.includes('github.io') 
  ? "https://iot-data-science-project-sxsx.vercel.app/"  // Replace with your Vercel URL
  : "/api/chat";  // For Vercel deployment

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

function getSessionId() {
  return localStorage.getItem("session_id") || "";
}

function setSessionId(id) {
  if (id) localStorage.setItem("session_id", id);
}

async function sendToBot(message) {
  const res = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": getSessionId()
    },
    body: JSON.stringify({ message, session_id: getSessionId() })
  });
  const data = await res.json();
  if (data.session_id) setSessionId(data.session_id);
  return data.reply || "(no reply)";
}

async function fetchBookings() {
  const sessionId = getSessionId();
  if (!sessionId) {
    bookingList.innerHTML = "<div class=\"booking-meta\">No session yet.</div>";
    return;
  }
  const res = await fetch(`${API_URL.replace("/chat", "")}/bookings?session_id=${encodeURIComponent(sessionId)}`);
  const data = await res.json();
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
    const detailPreview = detailKeys.slice(0, 2).map((k) => `${k}: ${b.details[k]}`).join(" • ");
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
  await fetch(`${API_URL.replace("/chat", "")}/bookings/${id}?session_id=${encodeURIComponent(sessionId)}`, {
    method: "DELETE"
  });
}

async function openBooking(id) {
  const sessionId = getSessionId();
  if (!sessionId) {
    modalError.textContent = "Missing session. Try sending a message first.";
    modal.classList.remove("hidden");
    return;
  }
  const res = await fetch(`${API_URL.replace("/chat", "")}/bookings/${id}?session_id=${encodeURIComponent(sessionId)}`);
  const data = await res.json();
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
  const res = await fetch(`${API_URL.replace("/chat", "")}/bookings/${activeBookingId}?session_id=${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
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
  await fetch(`${API_URL.replace("/chat", "")}/history/clear?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST"
  });
  chat.innerHTML = "";
  addMsg("Bot", "Chat history cleared. Happy now?");
}

async function fetchClinicInfo() {
  const res = await fetch(`${API_URL.replace("/chat", "")}/clinic/info`);
  const data = await res.json();
  const clinic = data.clinic || {};
  const services = (clinic.services || []).map((s) => {
    const bits = [s.name];
    if (s.duration_minutes) bits.push(`${s.duration_minutes} min`);
    if (s.price_sgd != null) bits.push(`SGD ${s.price_sgd}`);
    return bits.join(" • ");
  });
  if (services.length) {
    addMsg("Bot", "Services available:\n- " + services.join("\n- "));
  }
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
    addMsg("Bot", "Error calling backend. Check terminal logs.");
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
fetchClinicInfo().catch(() => {
  addMsg("Bot", "I couldn't load the service list right now.");
});
fetchBookings();
