// Paste your API Gateway endpoint here:
const API_URL = "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/chat";

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
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function sendToBot(message) {
  const res = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });

  const data = await res.json();
  if (!res.ok) {
    return `Error: ${data.error || JSON.stringify(data)}`;
  }
  return data.reply || "(no reply)";
}

async function onSend() {
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  addMsg("You", text);
  addMsg("Bot", "Typing...");

  // remove the typing line after response
  const typingNode = chat.lastChild;

  try {
    const reply = await sendToBot(text);
    typingNode.remove();
    addMsg("Bot", reply);
  } catch (e) {
    typingNode.remove();
    addMsg("Bot", "Failed to call API. Check API_URL / CORS / Lambda logs.");
    console.error(e);
  }
}

btn.addEventListener("click", onSend);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") onSend();
});

addMsg("Bot", "Hi! Ask me anything. (This is OpenAI via Lambda + API Gateway)");
