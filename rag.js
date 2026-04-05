// 🔥 LIVE API URL
const API = "https://annuall-reportrag-5.onrender.com";

let ready = false;

// Elements
const fileInput = document.getElementById("fileInput");
const questionInput = document.getElementById("question");
const chatBox = document.getElementById("chatBox");
const status = document.getElementById("status");

// Disable question initially
questionInput.disabled = true;

// =========================
// 📤 UPLOAD PDF
// =========================
fileInput.onchange = async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    status.innerText = "Uploading PDF... ⏳";

    try {
        const res = await fetch(`${API}/upload`, {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        console.log(data);

        if (!res.ok || data.error) {
            throw new Error(data.error || "Upload failed");
        }

        // ✅ Success
        status.innerText = `✅ PDF uploaded successfully (${data.chunks} chunks)`;
        ready = true;
        questionInput.disabled = false;

    } catch (err) {
        console.error(err);
        status.innerText = "❌ Upload failed: " + err.message;
    }
};

// =========================
// ❓ ASK QUESTION
// =========================
async function askQuestion() {
    const question = questionInput.value.trim();
    if (!question) return;

    if (!ready) {
        alert("⚠️ Upload PDF first!");
        return;
    }

    // Show user message
    chatBox.innerHTML += `
        <div class="message user">
            You: ${question}
        </div>
    `;
    questionInput.value = "";

    // Show loading
    const loadingMsg = document.createElement("div");
    loadingMsg.className = "message bot";
    loadingMsg.innerText = "Thinking... 🤖";
    chatBox.appendChild(loadingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const res = await fetch(`${API}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await res.json();
        console.log(data);

        if (!res.ok || data.error) {
            throw new Error(data.error || "Error getting answer");
        }

        // Remove loading message
        loadingMsg.remove();

        // ✅ Format sources correctly
        let sourcesHTML = "";
        if (data.sources && data.sources.length > 0) {
            sourcesHTML = data.sources.map(s =>
                `📄 Page ${s.page}: ${s.text}...`
            ).join("<br>");
        }

        // Show answer
        chatBox.innerHTML += `
            <div class="message bot">
                <div><b>Answer:</b> ${data.answer}</div>
                <div style="margin-top:8px; font-size:12px; color:#222;">
                    ${sourcesHTML}
                </div>
            </div>
        `;

        chatBox.scrollTop = chatBox.scrollHeight;

    } catch (err) {
        console.error(err);
        loadingMsg.remove();

        chatBox.innerHTML += `
            <div class="message bot">
                ❌ Error: ${err.message}
            </div>
        `;
        chatBox.scrollTop = chatBox.scrollHeight;
    }
}

// =========================
// ⌨️ Enter key support
// =========================
questionInput.addEventListener("keyup", function(e) {
    if (e.key === "Enter") {
        askQuestion();
    }
});
