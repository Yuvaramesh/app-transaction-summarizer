/* Ajeer – Recipient Risk Verification (MongoDB-backed) */

// ── Element refs ──────────────────────────────────────────────────────────────
const form         = document.getElementById("transferForm");
const verifyBtn    = document.getElementById("verifyBtn");
const btnText      = verifyBtn.querySelector(".btn-text");
const btnSpinner   = verifyBtn.querySelector(".btn-spinner");

const senderSel    = document.getElementById("sender_id");
const recipientSel = document.getElementById("recipient_id");
const senderBadge  = document.getElementById("senderBadge");
const recipientBadge = document.getElementById("recipientBadge");

const resultIdle   = document.getElementById("resultIdle");
const resultCard   = document.getElementById("resultCard");
const resultError  = document.getElementById("resultError");
const errorMsg     = document.getElementById("errorMsg");

// In-memory cache of DB data
let sendersCache    = [];
let recipientsCache = [];

// ── Bootstrap: load senders from DB ──────────────────────────────────────────
async function loadSenders() {
  try {
    const res  = await fetch("/api/senders");
    sendersCache = await res.json();

    senderSel.innerHTML = '<option value="">Select sender…</option>';
    sendersCache.forEach(s => {
      const opt = document.createElement("option");
      opt.value       = s._id;
      opt.textContent = `${s.full_name} (${s._id})`;
      senderSel.appendChild(opt);
    });
  } catch (e) {
    senderSel.innerHTML = '<option value="">Failed to load senders</option>';
    console.error("loadSenders:", e);
  }
}

// ── On sender change → show badge + load recipients ─────────────────────────
senderSel.addEventListener("change", async () => {
  const sid = senderSel.value;
  if (!sid) {
    senderBadge.hidden = true;
    recipientSel.innerHTML = '<option value="">Select a sender first…</option>';
    recipientBadge.hidden = true;
    return;
  }

  // Show sender badge
  const sender = sendersCache.find(s => s._id === sid);
  if (sender) {
    document.getElementById("badgeAge").textContent     = sender.account_age_label || "—";
    document.getElementById("badgeTypical").textContent = `£${sender.typical_transfer_amount}`;
    document.getElementById("badgeLimit").textContent   = `£${sender.monthly_limit_gbp}`;
    document.getElementById("badgeTotal").textContent   = sender.total_transfers;
    document.getElementById("badgeKyc").textContent     = sender.kyc_status;
    senderBadge.hidden = false;
  }

  // Load recipients for this sender
  try {
    recipientSel.innerHTML = '<option value="">Loading…</option>';
    recipientBadge.hidden = true;

    const res = await fetch(`/api/recipients?sender_id=${encodeURIComponent(sid)}`);
    recipientsCache = await res.json();

    recipientSel.innerHTML = '<option value="">Select recipient…</option>';
    if (recipientsCache.length === 0) {
      recipientSel.innerHTML = '<option value="">No recipients for this sender</option>';
    } else {
      recipientsCache.forEach(r => {
        const opt = document.createElement("option");
        opt.value       = r._id;
        opt.textContent = `${r.display_name} · ${r.country}`;
        recipientSel.appendChild(opt);
      });
    }
  } catch (e) {
    recipientSel.innerHTML = '<option value="">Failed to load</option>';
    console.error("loadRecipients:", e);
  }
});

// ── On recipient change → show recipient badge ────────────────────────────────
recipientSel.addEventListener("change", () => {
  const rid = recipientSel.value;
  if (!rid) { recipientBadge.hidden = true; return; }

  const r = recipientsCache.find(x => x._id === rid);
  if (r) {
    document.getElementById("rbBank").textContent    = r.bank;
    document.getElementById("rbCountry").textContent = r.country;
    document.getElementById("rbAccount").textContent = r.account_masked;
    document.getElementById("rbCurrency").textContent = r.destination_currency;
    document.getElementById("rbDays").textContent    = `${r.days_since_added} days`;
    recipientBadge.hidden = false;
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function getInitials(name) {
  return name.split(/[\s·]+/).filter(Boolean).slice(0, 2)
    .map(w => w[0].toUpperCase()).join("");
}

function setLoading(on) {
  btnText.hidden    = on;
  btnSpinner.hidden = !on;
  verifyBtn.disabled = on;
}

function showIdle() {
  resultIdle.hidden = false;
  resultCard.hidden = true;
  resultError.hidden = true;
}

function showError(msg) {
  resultIdle.hidden = true;
  resultCard.hidden = true;
  resultError.hidden = false;
  errorMsg.textContent = msg;
}

const TIER_ICONS = { green: "✓", amber: "!", red: "✕" };

// ── Render result card ────────────────────────────────────────────────────────
function renderResult(data) {
  const tier = data.tier;
  const meta = data._meta || {};

  // Tier tabs
  document.querySelectorAll(".tier-tab").forEach(tab => {
    tab.className = "tier-tab";
    if (tab.dataset.tier === tier) tab.classList.add(`active-${tier}`);
  });

  // Recipient header
  const name = meta.recipient_name || "Recipient";
  document.getElementById("recipientAvatar").textContent = getInitials(name);
  document.getElementById("recipientName").textContent   = name;
  document.getElementById("recipientMeta").textContent   =
    `${meta.recipient_bank || ""} · ${meta.recipient_country || ""} · ${meta.account_masked || ""}`;

  // Amount
  const amountInput = parseFloat(document.getElementById("amount").value) || 0;
  const converted   = document.getElementById("converted_amount").value;
  const recipientFirst = name.split(/[\s·]+/)[0];

  document.getElementById("amountGbp").textContent =
    `£${amountInput.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;
  document.getElementById("amountLocal").textContent =
    `${recipientFirst} receives ${converted} ${meta.destination_currency || ""}`;

  // Verdict banner
  const banner = document.getElementById("verdictBanner");
  banner.className = `verdict-banner tier-${tier}`;
  const icon = document.getElementById("verdictIcon");
  icon.className = `verdict-icon tier-${tier}`;
  icon.textContent = TIER_ICONS[tier];
  const headline = document.getElementById("verdictHeadline");
  headline.className = `verdict-headline tier-${tier}`;
  headline.textContent = data.headline;
  document.getElementById("verdictSummary").textContent = data.summary;

  // Signals
  const list = document.getElementById("signalsList");
  list.innerHTML = "";
  (data.signals || []).forEach(sig => {
    const li = document.createElement("li");
    li.className = "signal-item";
    li.innerHTML = `<span class="signal-dot ${sig.status}"></span><span>${sig.text}</span>`;
    list.appendChild(li);
  });

  // Risk bar
  const score = data.risk_score;
  const scoreLabel = tier === "green" ? "Low" : tier === "amber" ? "Medium" : "High";
  const rv = document.getElementById("riskValue");
  rv.className = `risk-value tier-${tier}`;
  rv.textContent = `${scoreLabel} · ${score}/100`;
  const fill = document.getElementById("riskBarFill");
  fill.className = `risk-bar-fill tier-${tier}`;
  fill.style.width = "0%";
  setTimeout(() => { fill.style.width = `${score}%`; }, 60);

  // DB context strip
  const strip = document.getElementById("dbStrip");
  strip.innerHTML = "";
  const chips = [
    ["Sender", meta.sender_name],
    ["Past transfers", meta.past_transfer_count],
    ["Monthly sent", meta.monthly_sent != null ? `£${meta.monthly_sent.toFixed(0)}` : "—"],
    ["Monthly limit", meta.monthly_limit != null ? `£${meta.monthly_limit}` : "—"],
  ];
  chips.forEach(([label, val]) => {
    const chip = document.createElement("div");
    chip.className = "db-chip";
    chip.innerHTML = `${label}: <span>${val ?? "—"}</span>`;
    strip.appendChild(chip);
  });

  // Actions
  const actionRow = document.getElementById("actionRow");
  actionRow.innerHTML = "";

  if (data.secondary_label) {
    const sec = document.createElement("button");
    sec.className = "btn-secondary";
    sec.textContent = data.secondary_label;
    sec.onclick = () => showIdle();
    actionRow.appendChild(sec);
  }

  const pri = document.createElement("button");
  pri.className = `btn-primary-${tier}`;
  pri.textContent = data.action_label || "Confirm transfer";
  pri.onclick = () => alert(`Action: ${data.action_label}`);
  actionRow.appendChild(pri);

  // Show
  resultIdle.hidden = true;
  resultError.hidden = true;
  resultCard.hidden = false;
}

// ── Form submit ───────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setLoading(true);

  const payload = {
    sender_id:        document.getElementById("sender_id").value,
    recipient_id:     document.getElementById("recipient_id").value,
    amount:           parseFloat(document.getElementById("amount").value) || 0,
    converted_amount: document.getElementById("converted_amount").value,
  };

  try {
    const res  = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "API error");
    renderResult(data);
  } catch (err) {
    showError(`Error: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────
loadSenders();
