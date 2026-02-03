const crawlBtn = document.getElementById("crawlBtn");
const resultBox = document.getElementById("result");

crawlBtn.addEventListener("click", async () => {
  resultBox.value = "Crawling...";

  // Get current tab URL
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab.url;

  try {
    const formData = new FormData();
    formData.append("url", url);

    const response = await fetch("http://127.0.0.1:8000/crawl", {
      method: "POST",
      body: formData
    });

    const html = await response.text();

    // grab textarea content from returned HTML
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const textarea = doc.querySelector("textarea");

    resultBox.value = textarea ? textarea.value : "No result found.";

  } catch (err) {
    resultBox.value = "Error:\n" + err.toString();
  }
});
