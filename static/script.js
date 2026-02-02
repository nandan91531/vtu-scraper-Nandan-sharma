document.addEventListener("DOMContentLoaded", () => {
  // --- Configuration ---
  // window.location.origin use karne se ye apne aap Render ka URL utha lega
  const API_URL = window.location.origin + "/api/vtu/results";
  console.log("Connected to Backend at:", API_URL);

  // --- DOM Elements ---
  const usnInput = document.getElementById("usn-input");
  const subjectCodeInput = document.getElementById("subject-code-input");
  
  const indexUrlInput = document.getElementById("index-url-input");
  const resultUrlInput = document.getElementById("result-url-input");
  
  const fetchButton = document.getElementById("fetch-button");
  const buttonText = document.getElementById("button-text"); 
  const loadingSpinner = document.getElementById("loading-spinner");
  
  const statusMessage = document.getElementById("status-message");
  const summaryOutput = document.getElementById("summary-output");
  const failedOutput = document.getElementById("failed-output");

  // Generator Elements
  const usnPrefix = document.getElementById("usn-prefix");
  const usnStart = document.getElementById("usn-start");
  const usnEnd = document.getElementById("usn-end");
  const generateButton = document.getElementById("generate-button");

  // --- Utility Functions ---

  function generateUSNs(prefix, start, end) {
    const generatedList = [];
    const FIXED_PADDING_LENGTH = 3; 

    for (let i = start; i <= end; i++) {
      const paddedNumber = String(i).padStart(FIXED_PADDING_LENGTH, "0");
      generatedList.push(`${prefix.toUpperCase()}${paddedNumber}`);
    }
    return generatedList;
  }

  function cleanUSNInput(rawText) {
    const normalizedText = rawText.replace(/[\n,;]+/g, "|").replace(/\s+/g, "");
    return normalizedText
      .split("|")
      .map((usn) => usn.trim().toUpperCase())
      .filter((usn, index, self) => usn && self.indexOf(usn) === index);
  }

  function updateStatus(message, type = "initial", isHtml = false) {
    statusMessage.className = `message-box ${type}`;
    if (isHtml) {
      statusMessage.innerHTML = message;
    } else {
      statusMessage.textContent = message;
    }
  }

  function hideOutputs() {
    summaryOutput.classList.add("hidden");
    failedOutput.classList.add("hidden");
    summaryOutput.innerHTML = "";
    failedOutput.innerHTML = "";
  }

  function setLoading(isLoading) {
    fetchButton.disabled = isLoading;
    if (isLoading) {
      loadingSpinner.style.display = "inline-block";
      buttonText.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Processing Results...';
    } else {
      loadingSpinner.style.display = "none";
      buttonText.innerHTML = '<i class="fas fa-file-download"></i> Fetch & Generate Excel';
    }
  }

  // --- Event Listeners ---

  generateButton.addEventListener("click", () => {
    const prefix = usnPrefix.value.trim();
    const start = parseInt(usnStart.value, 10);
    const end = parseInt(usnEnd.value, 10);

    if (!prefix || prefix.length < 5) {
      alert("Please enter a valid USN prefix (e.g., 1BI23EC).");
      return;
    }
    if (isNaN(start) || isNaN(end) || start < 1 || end < start) {
      alert("Please enter valid starting and ending numbers.");
      return;
    }

    const generatedList = generateUSNs(prefix, start, end);
    const currentContent = usnInput.value.trim();
    usnInput.value = currentContent ? currentContent + ", " + generatedList.join(", ") : generatedList.join(", ");

    updateStatus(`✅ Generated **${generatedList.length} USNs**.`, "success", true);
  });

  fetchButton.addEventListener("click", async () => {
    const usnList = cleanUSNInput(usnInput.value);
    const subjectCode = subjectCodeInput.value.trim().toUpperCase();
    const indexUrl = indexUrlInput.value.trim();
    const resultUrl = resultUrlInput.value.trim();

    hideOutputs();

    if (usnList.length === 0) {
      updateStatus("Please enter at least one valid USN.", "failure");
      return;
    }

    setLoading(true);
    updateStatus(`⏳ Scraping **${usnList.length} USNs**... Please wait.`, "initial", true);

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          usns: usnList,
          subject_code: subjectCode,
          index_url: indexUrl,
          result_url: resultUrl,
        }),
      });

      const data = await response.json();

      if (data.status === "success" && data.total_successful > 0) {
        let statusMsg = `✅ **Done!** Successful: **${data.total_successful}**, Failed: **${data.failed_count}**`;
        
        if (data.download_url) {
          statusMsg += `<br><br>💾 <a href="${data.download_url}" target="_blank" class="download-link">Click here to Download Excel</a>`;
        }
        updateStatus(statusMsg, "success", true);

        summaryOutput.innerHTML = `
            <p><strong>Total Requested:</strong> ${usnList.length}</p>
            <p><strong>Success:</strong> ${data.total_successful}</p>
            <p><strong>Failed:</strong> ${data.failed_count}</p>
        `;
        summaryOutput.classList.remove("hidden");
      } else {
        throw new Error("No results found or CAPTCHA error.");
      }

    } catch (error) {
      updateStatus(`❌ Error: ${error.message}`, "failure");
    } finally {
      setLoading(false);
    }
  });
});
