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
        const res = await fetch("http://127.0.0.1:8000/upload", {
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
    chatBox.innerHTML += `
        <div class="message bot">Thinking... 🤖</div>
    `;
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const res = await fetch("http://127.0.0.1:8000/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await res.json();
        console.log(data);

        if (!res.ok || data.error) {
            throw new Error(data.error || "Error getting answer");
        }

        // Remove "Thinking..." message
        const botMessages = document.querySelectorAll(".bot");
        if (botMessages.length) botMessages[botMessages.length - 1].remove();

        // ✅ Render final answer + single source
        let sourceHTML = "";
        if (data.source) {
            sourceHTML = `
                📄 Page ${data.source.page}<br>
                ${data.source.text}...
            `;
        }

        chatBox.innerHTML += `
            <div class="message bot">
                <div><b>Answer:</b> ${data.answer}</div>
                <div style="margin-top:8px; font-size:12px; color:#222;">
                    ${sourceHTML}
                </div>
            </div>
        `;
        chatBox.scrollTop = chatBox.scrollHeight;

    } catch (err) {
        console.error(err);
        chatBox.innerHTML += `
            <div class="message bot">
                ❌ Error: ${err.message}
            </div>
        `;
        chatBox.scrollTop = chatBox.scrollHeight;
    }
}

// =========================
// Press Enter to ask question
// =========================
questionInput.addEventListener("keyup", function(e) {
    if (e.key === "Enter") {
        askQuestion();
    }
}); 