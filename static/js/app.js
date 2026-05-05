/* ── Ajeer AI Transaction Summarizer · Frontend ───────────── */

const btnGenerate = document.getElementById("btn-generate");
const btnExport = document.getElementById("btn-export");
const monthSelect = document.getElementById("month-select");
const loading = document.getElementById("loading");
const errorBlock = document.getElementById("error-block");
const errorMsg = document.getElementById("error-msg");
const output = document.getElementById("summary-output");

let lastSummary = null;

// ── Generate ────────────────────────────────────────────────
btnGenerate.addEventListener("click", async () => {
  const month = parseInt(monthSelect.value);
  const year = 2026;

  setLoading(true);
  clearError();
  output.classList.add("hidden");
  btnExport.disabled = true;

  try {
    const res = await fetch("/api/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ month, year }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Failed to generate summary.");
    }

    lastSummary = await res.json();
    renderSummary(lastSummary);
    output.classList.remove("hidden");
    btnExport.disabled = false;
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
});

// ── Export PDF ──────────────────────────────────────────────
btnExport.addEventListener("click", async () => {
  const month = parseInt(monthSelect.value);
  btnExport.disabled = true;
  btnExport.textContent = "Generating…";

  try {
    const res = await fetch("/api/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ month, year: 2026 }),
    });

    if (!res.ok) throw new Error("PDF generation failed.");

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Ajeer_Statement_2026_${String(month).padStart(2, "0")}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showError(e.message);
  } finally {
    btnExport.disabled = false;
    btnExport.textContent = "Export PDF";
  }
});

// ── Render ──────────────────────────────────────────────────
function renderSummary(s) {
  const m = s.metrics;

  // Header
  document.getElementById("card-month-label").textContent =
    `${s.month_name} ${s.year}`;

  // Narrative
  document.getElementById("narrative-text").textContent = s.narrative;

  // Metrics
  document.getElementById("m-total-gbp").textContent =
    `£${m.total_gbp.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;
  document.getElementById("m-mom").textContent =
    `${m.mom_change_gbp >= 0 ? "+" : ""}£${m.mom_change_gbp.toFixed(2)} vs last month`;

  const receivedStr = Object.entries(m.received_by_currency)
    .map(
      ([ccy, v]) =>
        `${v.toLocaleString("en-GB", { minimumFractionDigits: 0 })} ${ccy}`,
    )
    .join(" · ");
  document.getElementById("m-received").textContent = receivedStr;
  document.getElementById("m-rate-change").textContent =
    `${m.rate_change_pct >= 0 ? "+" : ""}${m.rate_change_pct}% rate vs last month`;

  document.getElementById("m-fees").textContent = `£${m.total_fees.toFixed(2)}`;
  document.getElementById("m-fee-rate").textContent =
    `${m.transfer_count} transfer${m.transfer_count !== 1 ? "s" : ""}`;

  // Rate bars
  renderRateBars(s.rates);

  // Nudge
  document.getElementById("nudge-text").textContent = s.nudge;

  // Transactions
  renderTransactions(s.transactions);
}

function renderRateBars(rates) {
  const lkr = rates.LKR;
  const bars = [
    { label: `${currentMonthName()} 2026`, val: lkr.current, color: "#1D9E75" },
    { label: "Last month", val: lkr.prev_month, color: "#5DCAA5" },
    { label: "2 months ago", val: lkr.two_months_ago, color: "#9FE1CB" },
  ];
  const maxVal = Math.max(...bars.map((b) => b.val));
  const container = document.getElementById("rate-bars");
  container.innerHTML = "";

  bars.forEach((b) => {
    if (!b.val) return;
    const pct = ((b.val / maxVal) * 96).toFixed(1);
    container.innerHTML += `
      <div class="rate-bar-row">
        <span class="rate-bar-label">${b.label}</span>
        <div class="rate-bar-track">
          <div class="rate-bar-fill" style="width:${pct}%;background:${b.color};"></div>
        </div>
        <span class="rate-bar-val">${b.val.toFixed(2)}</span>
      </div>`;
  });
}

function renderTransactions(transactions) {
  const tbody = document.getElementById("txn-body");
  tbody.innerHTML = "";

  transactions.forEach((t) => {
    const statusClass =
      t.status === "Completed" ? "status-completed" : "status-processing";
    tbody.innerHTML += `
      <tr>
        <td class="txn-id">${t.transaction_id}</td>
        <td><strong>${t.recipient_name}</strong><br/><span style="color:#9CA3AF;font-size:11px;">${t.country}</span></td>
        <td>${t.date}</td>
        <td><strong>£${t.amount_gbp.toLocaleString("en-GB", { minimumFractionDigits: 2 })}</strong></td>
        <td>${t.amount_received.toLocaleString("en-GB", { minimumFractionDigits: 2 })} ${t.currency}</td>
        <td>${t.exchange_rate}</td>
        <td><span class="status-pill ${statusClass}">${t.status}</span></td>
      </tr>`;
  });
}

// ── Helpers ─────────────────────────────────────────────────
function setLoading(on) {
  loading.classList.toggle("hidden", !on);
  btnGenerate.disabled = on;
  btnGenerate.textContent = on ? "Generating…" : "Generate Summary";
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorBlock.classList.remove("hidden");
}

function clearError() {
  errorBlock.classList.add("hidden");
  errorMsg.textContent = "";
}

function currentMonthName() {
  const names = [
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return (
    names[parseInt(document.getElementById("month-select").value)] || "Apr"
  );
}
