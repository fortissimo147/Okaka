let DATA = null;
let chart = null;

const COLORS = [
  "#2196F3","#E91E63","#4CAF50","#FF9800","#9C27B0",
  "#00BCD4","#F44336","#8BC34A","#FF5722","#3F51B5",
  "#009688","#FFC107","#795548","#607D8B","#CDDC39",
  "#673AB7","#03A9F4","#76FF03","#FF4081","#FFD740",
];

async function load() {
  try {
    const res = await fetch("data/dashboard.json");
    if (!res.ok) throw new Error(res.statusText);
    DATA = await res.json();
    render();
  } catch (e) {
    document.getElementById("no-data").textContent = "データの読み込みに失敗しました: " + e.message;
  }
}

function render() {
  const app = document.getElementById("app");
  if (!DATA.dates || DATA.dates.length === 0) {
    document.getElementById("no-data").textContent = "データがありません。import_all.py を実行してください。";
    return;
  }
  document.getElementById("no-data").remove();
  document.getElementById("generated-at").textContent =
    "最終更新: " + DATA.generated_at.slice(0, 16).replace("T", " ");

  app.innerHTML = `
    <div class="card" id="section-changes">
      <h2>銘柄変動サマリ</h2>
      <div class="date-selector">
        <label>表示日:</label>
        <select id="change-date-select"></select>
      </div>
      <div class="change-grid" id="change-grid"></div>
    </div>

    <div class="card">
      <h2>保有割合 上位銘柄の推移（時系列）</h2>
      <div class="chart-container"><canvas id="timeseries-chart"></canvas></div>
    </div>

    <div class="card">
      <h2>過去10営業日 累積買い増し注目銘柄 <span class="subtitle">保有金額2,000万円以上 かつ 累積買い増し比率70%以上（基準日: ${DATA.strong_buys_base_date}）</span></h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th>累積買い増し比率</th>
              <th>基準日株数</th>
              <th>最新株数</th>
              <th>保有金額</th>
            </tr>
          </thead>
          <tbody id="strong-buys-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>全銘柄スナップショット（最新: ${DATA.latest_date}）</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th>保有比率 (%)</th>
              <th>前日比 (pp)</th>
              <th>保有株数</th>
            </tr>
          </thead>
          <tbody id="latest-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>過去20営業日 買い増し損益</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th>買い増し株数</th>
              <th>回数</th>
              <th>平均取得価格→現在価格</th>
              <th>損益率</th>
              <th>保有比率</th>
            </tr>
          </thead>
          <tbody id="buyup-pnl-tbody"></tbody>
        </table>
      </div>
    </div>
  `;

  renderChangeDateSelect();
  renderChart();
  renderStrongBuys();
  renderLatestTable();
  renderBuyupPnl();
}

function renderChangeDateSelect() {
  const sel = document.getElementById("change-date-select");
  DATA.changes.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.date;
    opt.textContent = c.date;
    sel.appendChild(opt);
  });
  if (DATA.changes.length > 0) {
    sel.value = DATA.changes[DATA.changes.length - 1].date;
    renderChangeGrid(sel.value);
  }
  sel.addEventListener("change", () => renderChangeGrid(sel.value));
}

function renderChangeGrid(date) {
  const change = DATA.changes.find(c => c.date === date);
  const grid = document.getElementById("change-grid");
  if (!change) { grid.innerHTML = ""; return; }

  grid.innerHTML = `
    <div class="change-section tag-new">
      <h3>新規追加 (${change.new.length})</h3>
      ${listItems(change.new, r => `<span class="ticker">${r.ticker}</span><span>${r.name}</span><span>${r.ratio.toFixed(2)}%</span>`)}
    </div>
    <div class="change-section tag-remove">
      <h3>処分 (${change.removed.length})</h3>
      ${listItems(change.removed, r => `<span class="ticker">${r.ticker}</span><span>${r.name}</span>`)}
    </div>
    <div class="change-section tag-up">
      <h3>買い増し (${change.increased.length})</h3>
      ${listItems(change.increased, r => `<span class="ticker">${r.ticker}</span><span>${r.name}</span><span class="delta-pos">+${r.delta.toFixed(1)}%</span>`)}
    </div>
    <div class="change-section tag-down">
      <h3>削減 (${change.decreased.length})</h3>
      ${listItems(change.decreased, r => `<span class="ticker">${r.ticker}</span><span>${r.name}</span><span class="delta-neg">${r.delta.toFixed(1)}%</span>`)}
    </div>
  `;
}

function listItems(items, rowFn) {
  if (items.length === 0) return `<p class="empty">なし</p>`;
  return `<ul class="change-list">${items.map(r => `<li>${rowFn(r)}</li>`).join("")}</ul>`;
}

function renderChart() {
  const labels = DATA.dates;
  const datasets = DATA.timeseries.map((t, i) => ({
    label: `${t.ticker} ${t.name}`,
    data: t.series.map(s => s.ratio),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: "transparent",
    tension: 0.2,
    pointRadius: 3,
    spanGaps: true,
  }));

  const ctx = document.getElementById("timeseries-chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "right", labels: { font: { size: 11 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) + "%" : "—"}`,
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 11 } } },
        y: { title: { display: true, text: "保有比率 (%)" }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

function renderStrongBuys() {
  const tbody = document.getElementById("strong-buys-tbody");
  if (!DATA.strong_buys || DATA.strong_buys.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty" style="padding:12px;text-align:center">該当銘柄なし</td></tr>`;
    return;
  }
  tbody.innerHTML = DATA.strong_buys.map(r => `
    <tr>
      <td>${r.ticker}</td>
      <td>${r.name}</td>
      <td><span class="delta-pos">+${r.cumulative_pct.toFixed(1)}%</span></td>
      <td>${r.base_shares.toLocaleString()}</td>
      <td>${r.shares.toLocaleString()}</td>
      <td>${(r.value / 1_000_000).toFixed(1)}百万円</td>
    </tr>
  `).join("");
}

function renderLatestTable() {
  const tbody = document.getElementById("latest-tbody");
  tbody.innerHTML = DATA.latest.map(r => `
    <tr>
      <td>${r.ticker}</td>
      <td>${r.name}${r.is_new ? '<span class="badge-new">NEW</span>' : ""}</td>
      <td>${r.ratio.toFixed(2)}</td>
      <td>${r.delta != null ? (r.delta >= 0 ? `<span class="delta-pos">+${r.delta.toFixed(2)}</span>` : `<span class="delta-neg">${r.delta.toFixed(2)}</span>`) : "—"}</td>
      <td>${r.shares != null ? r.shares.toLocaleString() : "—"}</td>
    </tr>
  `).join("");
}

function renderBuyupPnl() {
  const tbody = document.getElementById("buyup-pnl-tbody");
  if (!DATA.buyup_pnl || DATA.buyup_pnl.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty" style="padding:12px;text-align:center">該当銘柄なし</td></tr>`;
    return;
  }
  const fmt = v => "¥" + Math.round(v).toLocaleString();
  tbody.innerHTML = DATA.buyup_pnl.map(r => {
    const pct = r.pnl_pct * 100;
    const cls = pct >= 0 ? "delta-pos" : "delta-neg";
    const sign = pct >= 0 ? "+" : "";
    return `
      <tr>
        <td>${r.ticker}</td>
        <td>${r.name}</td>
        <td>${r.total_added_shares.toLocaleString()}</td>
        <td>${r.entries.length}</td>
        <td>${fmt(r.avg_entry_price)} → ${fmt(r.latest_price)}</td>
        <td><span class="${cls}">${sign}${pct.toFixed(2)}%</span></td>
        <td>${r.latest_ratio.toFixed(2)}%</td>
      </tr>
    `;
  }).join("");
}

load();
