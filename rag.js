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

        let data;
        try {
            data = await res.json();
        } catch {
            throw new Error("Server returned empty response (backend crash)");
        }

        console.log(data);

        if (!res.ok || data.error) {
            throw new Error(data.error || "Upload failed");
        }

        status.innerText = `✅ PDF uploaded (${data.chunks} chunks)`;
        ready = true;
        questionInput.disabled = false;

    } catch (err) {
        console.error(err);
        status.innerText = "❌ Upload failed: " + err.message;
    }
};
