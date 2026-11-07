// LinkedIn Profile Page Saver.
//
// Automatic mode: while `python run.py` is running, it serves a queue of profile pages on
// 127.0.0.1:8765. This worker asks for the next page, opens it in its own window in this
// browser (where you are already logged in), scrolls it, and posts the rendered HTML back.
// It pauses 5-9 seconds between pages and stops at the first LinkedIn checkpoint or login page.
// It does not hide that it is automated, solve challenges, or change the browser's identity.
//
// Manual mode: clicking the toolbar button saves the open profile page to
// Downloads/linkedin_capture/<slug>/<section>.html.

const SERVER = "http://127.0.0.1:8765";
const BLOCK_PATHS = ["/checkpoint", "/authwall", "/login", "/uas/"];
const SECTIONS = {
  "": "profile",
  "details/experience": "experience",
  "details/education": "education",
  "details/skills": "skills",
  "details/interests": "interests",
  "recent-activity/all": "activity",
};

let running = false;
let captureWindowId = null;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function captureTarget(url) {
  const { hostname, pathname } = new URL(url);
  if (hostname !== "linkedin.com" && !hostname.endsWith(".linkedin.com")) return null;
  const match = pathname.match(/^\/in\/([^/]+)\/?(.*?)\/?$/);
  if (!match || !(match[2] in SECTIONS)) return null;
  return { slug: decodeURIComponent(match[1]), section: SECTIONS[match[2]] };
}

// Runs inside the page. Scrolls so lazy sections load, then reports whether the section's content
// is on the page. LinkedIn loads a section only once it is on screen.
async function scrollAndCheck(scrollSteps, section) {
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  for (let i = 0; i < scrollSteps; i++) {
    window.scrollBy(0, 1200);
    const main = document.querySelector("main");
    if (main) main.lastElementChild?.scrollIntoView({ block: "end" });
    await pause(700);
  }
  // Long lists (e.g. 80 skills) load in batches as you scroll: keep going until the page stops growing.
  if (section && section !== "profile") {
    let size = -1;
    for (let i = 0; i < 20 && document.body.innerText.length !== size; i++) {
      size = document.body.innerText.length;
      window.scrollTo(0, document.body.scrollHeight);
      document.querySelector("main")?.lastElementChild?.scrollIntoView({ block: "end" });
      await pause(1200);
    }
  }
  window.scrollTo(0, 0);
  const main = document.querySelector("main") || document.body;
  if (/Nothing to see for now|hasn.t posted/.test(main.innerText || "")) return true;
  const titles = [...main.querySelectorAll("h2")].map((h) => h.innerText.trim().replace(/\s*\(\d+\)$/, ""));
  const card = main.querySelector('[componentkey^="com.linkedin.sdui.profile.card"]');
  switch (section) {
    case "profile": return ["Experience", "Education", "About"].some((t) => titles.includes(t));
    case "experience": return !!main.querySelector('[componentkey^="entity-collection-item"]');
    case "education": return !!card && card.querySelectorAll("[componentkey] p").length >= 2;
    case "skills": return !!main.querySelector('[componentkey^="com.linkedin.sdui.profile.skill"]');
    case "interests": return main.querySelectorAll('span[aria-hidden="true"]').length > 0;
    case "activity": return !!main.querySelector('[componentkey^="update-card"]');
    default: return true;
  }
}

// Runs inside the page. Returns the HTML without scripts, styles and images: the parser does not
// need them, and they carry session data.
function readPage() {
  const copy = document.documentElement.cloneNode(true);
  copy.querySelectorAll("script, style, svg, img, noscript").forEach((el) => el.remove());
  return copy.outerHTML;
}

async function inPage(tabId, func, args = []) {
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return result;
}

async function readTab(tabId, scrollSteps) {
  if (scrollSteps > 0) await inPage(tabId, scrollAndCheck, [scrollSteps, ""]);
  return inPage(tabId, readPage);
}

// Scrolls until the section's content shows. A hidden window does not load lazy sections, so
// after a failed try the capture window is brought to the front and the page scrolled again.
async function loadSection(tabId, section) {
  const steps = section === "profile" || section === "activity" ? 8 : 5;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (await inPage(tabId, scrollAndCheck, [steps, section])) return true;
    if (captureWindowId !== null) {
      await chrome.windows.update(captureWindowId, { focused: true, state: "normal" }).catch(() => {});
    }
    await sleep(2000);
  }
  return false;
}

function waitForLoad(tabId, timeoutMs) {
  return new Promise((resolve) => {
    const timer = setTimeout(finish, timeoutMs);
    function listener(id, info) {
      if (id === tabId && info.status === "complete") finish();
    }
    function finish() {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function api(path, body) {
  const options = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(SERVER + path, options);
  return response.json();
}

async function openInCaptureWindow(url) {
  if (captureWindowId !== null) {
    try {
      const [tab] = await chrome.tabs.query({ windowId: captureWindowId });
      if (tab) {
        await chrome.tabs.update(tab.id, { url });
        return tab.id;
      }
    } catch (error) {
      captureWindowId = null; // The window was closed.
    }
  }
  const win = await chrome.windows.create({ url, focused: false, width: 1280, height: 900 });
  captureWindowId = win.id;
  return win.tabs[0].id;
}

async function runQueue() {
  if (running) return;
  running = true;
  try {
    while (true) {
      let job;
      try {
        job = await api("/next");
      } catch (error) {
        return; // run.py is not running.
      }
      if (!job.task) return;

      const { url, slug, section } = job.task;
      const tabId = await openInCaptureWindow(url);
      await waitForLoad(tabId, 45000);
      await sleep(2500);

      const finalUrl = (await chrome.tabs.get(tabId)).url || "";
      if (BLOCK_PATHS.some((prefix) => new URL(finalUrl).pathname.startsWith(prefix))) {
        await api("/blocked", { token: job.token, url: finalUrl });
        return;
      }
      await loadSection(tabId, section); // The server re-asks for pages that still come back incomplete.
      const html = await inPage(tabId, readPage);
      await api("/result", { token: job.token, slug, section, html });

      const [low, high] = job.delay_range_s;
      await sleep((low + Math.random() * (high - low)) * 1000);
    }
  } finally {
    running = false;
  }
}

// Manual save: toolbar button.
async function saveOpenPage(tab) {
  const target = captureTarget(tab.url);
  if (!target) return { saved: false };
  const html = await readTab(tab.id, 0);
  await chrome.downloads.download({
    url: "data:text/html;charset=utf-8," + encodeURIComponent(html),
    filename: `linkedin_capture/${target.slug}/${target.section}.html`,
    conflictAction: "overwrite",
    saveAs: false,
  });
  return { saved: true, ...target };
}

chrome.action.onClicked.addListener(async (tab) => {
  let text = "!";
  let color = "#DC2626";
  try {
    if ((await saveOpenPage(tab)).saved) {
      text = "OK";
      color = "#059669";
    }
  } catch (error) {
    console.error(error);
  }
  await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color });
  await chrome.action.setBadgeText({ tabId: tab.id, text });
});

chrome.windows.onRemoved.addListener((id) => {
  if (id === captureWindowId) captureWindowId = null;
});

// Check for work on install, on browser start, and every 30 seconds.
chrome.alarms.create("poll", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(runQueue);
chrome.runtime.onStartup.addListener(runQueue);
chrome.runtime.onInstalled.addListener(runQueue);
runQueue();
