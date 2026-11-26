"use strict";

const byId = (id) => document.getElementById(id);
const profiles = [
  ["interrupted", "Disconnect at 70%"],
  ["stable", "Stable link"],
  ["latency", "200 ms per request"],
  ["small", "Small file"]
];
const percent = (x) => (100 * x).toFixed(1) + "%";
const points = (x) => (x < 0 ? "−" : x > 0 ? "+" : "") + Math.abs(100 * x).toFixed(1) + " pp";
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

async function showExperiment() {
  const [platform, run, release, audit] = await Promise.all(
    ["platform", "groups", "release", "reconciliation"].map(async (name) => {
      const response = await fetch("/data/" + name + ".json");
      if (!response.ok) throw new Error("Saved evidence unavailable");
      return response.json();
    })
  );
  const metrics = platform.results.payload.metrics;
  if (metrics.length !== 1 || platform.experiment_id !== release.id ||
      audit.experiment_id !== release.id || !audit.platform_agrees || !platform.results.is_final ||
      release.status !== "completed" || release.rollout_decision !== "control") {
    throw new Error("Inconsistent release inputs");
  }
  const arms = metrics[0].variants;
  for (const [key, shortName, title] of [
    ["control", "whole", "Whole-file retry"], ["resume", "resume", "64 KiB checkpoints"]
  ]) {
    const arm = arms[key];
    let enrolled = 0;
    let verified = 0;
    for (const [profile] of profiles) {
      const cell = run.groups[profile][shortName];
      if (!Number.isSafeInteger(cell.n) || !Number.isSafeInteger(cell.successes) ||
          cell.n <= 0 || cell.successes < 0 || cell.successes > cell.n ||
          Math.abs(cell.success_rate - cell.successes / cell.n) > 1e-9 ||
          !Number.isFinite(cell.success_rate)) throw new Error("Invalid profile counts");
      enrolled += cell.n;
      verified += cell.successes;
    }
    if (arm.n !== enrolled || arm.sum !== verified ||
        run.groups.overall[shortName].n !== enrolled || run.groups.overall[shortName].successes !== verified ||
        arm.n !== audit.assigned[shortName] || arm.sum !== audit.on_time_and_verified[shortName]) {
      throw new Error("Inconsistent transfer counts");
    }
    const card = document.createElement("article");
    card.className = "outcome " + key;
    card.append(element("h2", title), element("strong", percent(arm.sum / arm.n)),
      element("small", arm.sum + " of " + arm.n + " uploads verified on time"));
    byId("arms").append(card);
  }
  const rates = {};
  const planned = { interrupted: 80, stable: 40, latency: 20, small: 20 };
  for (const [key, title] of profiles) {
    const { whole, resume } = run.groups[key];
    if (whole.n + resume.n !== planned[key]) throw new Error("Profile size differs from the frozen workload");
    const delta = resume.successes / resume.n - whole.successes / whole.n;
    const row = byId("rows").insertRow();
    const label = element("th", title);
    label.scope = "row";
    row.append(label);
    for (const arm of [whole, resume]) row.insertCell().textContent = arm.successes + " / " + arm.n;
    row.insertCell().textContent = points(delta);
    row.dataset.harm = String(key !== "interrupted" && delta < -0.05);
    rates[key] = { whole: whole.successes / whole.n, resume: resume.successes / resume.n };
  }
  const { control, resume } = arms;
  const total = control.n + resume.n;
  if (audit.sessions_checked !== total) throw new Error("Unexpected number of audited sessions");
  byId("headline").textContent = "Keep whole-file retry.";
  byId("status").textContent = "Flagsmith experiment #" + release.id + " · " + total +
    " simulated visitors · Final flag value: " + release.flag.value;
  byId("delta").textContent = points(resume.sum / resume.n - control.sum / control.n) + " overall with checkpoints";
  byId("verified").textContent = (resume.sum + control.sum) + " conversions reconciled to receiver evidence";
  byId("harm").textContent = "At 200 ms per request, eight serial acknowledgements take 1.6 s before transfer time. The 1.25 s budget expires.";
  function updateMix() {
    const drop = Number(byId("mix-range").value) / 100;
    const weights = { interrupted: drop, stable: (1 - drop) / 2, latency: (1 - drop) / 4, small: (1 - drop) / 4 };
    const estimate = (arm) => profiles.reduce((sum, [key]) => sum + weights[key] * rates[key][arm], 0);
    byId("mix-percent").textContent = Math.round(drop * 100) + "%";
    byId("mix-population").textContent = "Remaining shares: stable " + percent(weights.stable) +
      ", high latency " + percent(weights.latency) + ", small files " + percent(weights.small) + ".";
    byId("mix-outcome").textContent = "Estimated completion: " + percent(estimate("whole")) +
      " whole file, " + percent(estimate("resume")) + " resume (" + points(estimate("resume") - estimate("whole")) + ").";
  }
  byId("mix-range").addEventListener("input", updateMix);
  updateMix();
  byId("findings").hidden = false;
}
showExperiment().catch(() => {
  byId("headline").textContent = "Experiment unavailable.";
  byId("status").textContent = "Check that the complete evidence directory is present, then refresh.";
});

const liveForm = byId("live-form");
liveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (byId("live-run").disabled) return;
  byId("live-run").disabled = true;
  byId("live-profile").disabled = true;
  const fields = byId("live-fields");
  fields.replaceChildren();
  fields.hidden = true;
  const status = byId("live-status");
  status.textContent = "Reading the flag and waiting for the server receipt…";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch("/api/release-check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: byId("live-profile").value }), signal: controller.signal
    });
    if (response.status === 503) {
      status.textContent = "Live Flagsmith unavailable. Connect the release-check server to its SDK environment and retry.";
      return;
    }
    if (response.status === 429) {
      status.textContent = "The transfer service is busy. Retry in a moment.";
      return;
    }
    if (!response.ok) throw new Error("Request failed");
    const data = await response.json();
    if (data.status === "disabled") {
      status.textContent = "Flagsmith disabled this feature. No upload started.";
      return;
    }
    const r = data.receipt;
    if (data.status !== "executed" || !r || !["whole","resume"].includes(data.strategy)) throw new Error("Unexpected receipt");
    status.textContent = r.success ? "File verified within the deadline." :
      r.reason === "deadline" ? "The upload missed the deadline." : "The upload did not verify on time.";
    const facts = [
      ["Flag", data.flag], ["Evaluated value", data.value], ["Strategy", data.strategy === "whole" ? "Whole-file retry" : "64 KiB checkpoints"],
      ["Bytes sent", (r.wire_bytes / 1024).toFixed(1) + " KiB"], ["Elapsed", Number(r.elapsed_ms).toFixed(0) + " ms"],
      ["Received SHA-256", r.sha256 || "Incomplete file"]
    ];
    for (const [label, text] of facts) fields.append(element("dt", label), element("dd", text));
    fields.hidden = false;
  } catch (error) {
    status.textContent = error.name === "AbortError" ? "The live check timed out. You can retry." : "The live check failed. Check the local server, then retry.";
  } finally {
    clearTimeout(timer);
    byId("live-run").disabled = false;
    byId("live-profile").disabled = false;
  }
});
