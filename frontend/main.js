const API_URL = "http://127.0.0.1:8000/chat";

const chat = document.getElementById("chat");
const input = document.getElementById("msg");
const btn = document.getElementById("sendBtn");

function addMsg(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + (who === "You" ? "you" : "bot");
  div.innerHTML = `<b>${who}:</b> ${escapeHtml(text)}`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(s) {
  return s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

async function sendToBot(message) {
  const res = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  const data = await res.json();
  return data.reply || "(no reply)";
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
  } catch (e) {
    typing.remove();
    addMsg("Bot", "Error calling backend. Check terminal logs.");
    console.error(e);
  }
}

btn.addEventListener("click", onSend);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") onSend(); });

addMsg("Bot", "Hi! This is running locally. Ask me anything.");
