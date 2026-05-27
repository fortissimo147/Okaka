let DATA = null;
let chart = null;
let tickerChart = null;

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

    <div class="card" id="section-timeseries">
      <h2>保有割合 上位銘柄の推移（時系列）</h2>
      <div class="chart-container"><canvas id="timeseries-chart"></canvas></div>
    </div>

    <div class="card" id="section-strong-buys">
      <h2>過去10営業日 累積買い増し注目銘柄 <span class="subtitle">保有金額2,000万円以上 かつ 累積買い増し比率70%以上（基準日: ${DATA.strong_buys_base_date}）</span></h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th data-key="cumulative_pct">累積買い増し比率</th>
              <th data-key="base_shares">基準日株数</th>
              <th data-key="shares">最新株数</th>
              <th data-key="value">保有金額</th>
            </tr>
          </thead>
          <tbody id="strong-buys-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card" id="section-trading-analysis">
      <h2>過去20営業日 売買分析</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th data-key="benchmark_pnl_pct">ベンチマーク損益率</th>
              <th data-key="actual_pnl_pct">実際の運用損益率</th>
              <th data-key="evaluation_pct">評価（実際-ベンチマーク）</th>
              <th>買い増し回数</th>
              <th>売却回数</th>
              <th>保有比率</th>
            </tr>
          </thead>
          <tbody id="trading-analysis-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card" id="section-unrealized">
      <h2>推測含み益 <span class="subtitle">加重平均取得原価と最新株価の差額 / ${DATA.unrealized_gains?.baseline_date ?? ""}比較で株数が減った銘柄は除外</span></h2>
      <div id="unrealized-summary" style="font-size:1.4rem;font-weight:700;padding:8px 0 16px"></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th><th>銘柄名</th>
              <th data-key="shares">保有株数</th>
              <th data-key="avg_cost">平均取得単価</th>
              <th data-key="latest_price">最新株価</th>
              <th data-key="unrealized_pct">含み損益率</th>
              <th data-key="unrealized">推測含み損益</th>
            </tr>
          </thead>
          <tbody id="unrealized-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card" id="section-snapshot">
      <h2>全銘柄スナップショット（最新: ${DATA.latest_date}）</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>コード</th>
              <th>銘柄名</th>
              <th data-key="ratio">保有比率 (%)</th>
              <th data-key="delta">前日比 (pp)</th>
              <th data-key="shares">保有株数</th>
              <th data-key="value">保有金額</th>
            </tr>
          </thead>
          <tbody id="latest-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card" id="section-fund-cash">
      <h2>ファンド現金・資産推移</h2>
      <div style="display:flex;flex-direction:column;gap:24px;padding:4px 0">
        <div>
          <div style="font-size:12px;color:#888;margin-bottom:6px">① Fund Cash Component 推移</div>
          <div style="position:relative;height:180px"><canvas id="chart-cash"></canvas></div>
        </div>
        <div>
          <div style="font-size:12px;color:#888;margin-bottom:6px">② ファンド総資産推移（株式時価総額 + Fund Cash Component）</div>
          <div style="position:relative;height:180px"><canvas id="chart-nav"></canvas></div>
        </div>
        <div>
          <div style="font-size:12px;color:#888;margin-bottom:6px">③ 現金比率推移（Fund Cash Component ÷ 総資産）</div>
          <div style="position:relative;height:180px"><canvas id="chart-cash-ratio"></canvas></div>
        </div>
      </div>
    </div>

    <div class="card" id="section-search">
      <h2>銘柄データ検索</h2>
      <div class="search-box">
        <input type="text" id="ticker-search" placeholder="銘柄コードまたは社名で検索..." />
        <div id="search-suggestions"></div>
      </div>
      <div id="search-result"></div>
    </div>
  `;

  renderChangeDateSelect();
  renderChart();
  renderStrongBuys();
  renderTradingAnalysis();
  renderUnrealizedGains();
  renderLatestTable();
  renderFundCashCharts();
  renderSearch();
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

function makeSortable(tbodyId, getData, renderRowFn) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const thead = tbody.closest("table").querySelector("thead tr");
  let sortKey = null, sortAsc = true;
  thead.querySelectorAll("th[data-key]").forEach(th => {
    th.dataset.label = th.textContent;
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      sortAsc = sortKey === key ? !sortAsc : false;
      sortKey = key;
      thead.querySelectorAll("th[data-key]").forEach(h => { h.textContent = h.dataset.label; });
      th.textContent = th.dataset.label + (sortAsc ? " ▲" : " ▼");
      const sorted = [...getData()].sort((a, b) => {
        const av = a[key], bv = b[key];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return sortAsc ? av - bv : bv - av;
      });
      tbody.innerHTML = sorted.map(renderRowFn).join("");
    });
  });
}

function renderStrongBuys() {
  const tbody = document.getElementById("strong-buys-tbody");
  const data = DATA.strong_buys || [];
  if (data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty" style="padding:12px;text-align:center">該当銘柄なし</td></tr>`;
    return;
  }
  const rowFn = r => `
    <tr>
      <td>${r.ticker}</td>
      <td>${r.name}</td>
      <td><span class="delta-pos">+${r.cumulative_pct.toFixed(1)}%</span></td>
      <td>${r.base_shares.toLocaleString()}</td>
      <td>${r.shares.toLocaleString()}</td>
      <td>${(r.value / 1_000_000).toFixed(1)}百万円</td>
    </tr>
  `;
  tbody.innerHTML = data.map(rowFn).join("");
  makeSortable("strong-buys-tbody", () => DATA.strong_buys || [], rowFn);
}

function renderUnrealizedGains() {
  const ug = DATA.unrealized_gains;
  if (!ug) return;
  const total = ug.total;
  const color = total >= 0 ? "#4caf50" : "#ef5350";
  document.getElementById("unrealized-summary").innerHTML =
    `推測含み損益合計: <span style="color:${color}">${total >= 0 ? "+" : ""}${(total / 1_000_000).toFixed(1)}百万円</span>`;
  const rowFn = r => {
    const pctColor = r.unrealized_pct >= 0 ? "#4caf50" : "#ef5350";
    const valColor = r.unrealized >= 0 ? "#4caf50" : "#ef5350";
    return `<tr>
      <td>${r.ticker}</td>
      <td>${r.name}</td>
      <td style="text-align:right">${r.shares.toLocaleString()}</td>
      <td style="text-align:right">${r.avg_cost.toLocaleString()}</td>
      <td style="text-align:right">${r.latest_price.toLocaleString()}</td>
      <td style="text-align:right;color:${pctColor}">${r.unrealized_pct >= 0 ? "+" : ""}${r.unrealized_pct.toFixed(2)}%</td>
      <td style="text-align:right;color:${valColor}">${r.unrealized >= 0 ? "+" : ""}${(r.unrealized / 1_000_000).toFixed(2)}百万円</td>
    </tr>`;
  };
  document.getElementById("unrealized-tbody").innerHTML = (ug.items || []).map(rowFn).join("");
  makeSortable("unrealized-tbody", () => ug.items || [], rowFn);
}

function renderLatestTable() {
  const rowFn = r => `
    <tr>
      <td>${r.ticker}</td>
      <td>${r.name}${r.is_new ? '<span class="badge-new">NEW</span>' : ""}</td>
      <td>${r.ratio.toFixed(2)}</td>
      <td>${r.delta != null ? (r.delta >= 0 ? `<span class="delta-pos">+${r.delta.toFixed(2)}</span>` : `<span class="delta-neg">${r.delta.toFixed(2)}</span>`) : "—"}</td>
      <td>${r.shares != null ? r.shares.toLocaleString() : "—"}</td>
      <td>${r.value != null ? (r.value / 1_000_000).toFixed(1) + "百万円" : "—"}</td>
    </tr>
  `;
  document.getElementById("latest-tbody").innerHTML = (DATA.latest || []).map(rowFn).join("");
  makeSortable("latest-tbody", () => DATA.latest || [], rowFn);
}

function renderTradingAnalysis() {
  const tbody = document.getElementById("trading-analysis-tbody");
  const data = DATA.trading_analysis || [];
  if (data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty" style="padding:12px;text-align:center">該当銘柄なし</td></tr>`;
    return;
  }
  const fmtPct = v => { const p = v * 100; return `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`; };
  const rowFn = r => {
    const evalCls = r.evaluation_pct >= 0 ? "delta-pos" : "delta-neg";
    const benchCls = r.benchmark_pnl_pct >= 0 ? "delta-pos" : "delta-neg";
    const actualCls = r.actual_pnl_pct >= 0 ? "delta-pos" : "delta-neg";
    return `
      <tr>
        <td>${r.ticker}</td>
        <td>${r.name}</td>
        <td><span class="${benchCls}">${fmtPct(r.benchmark_pnl_pct)}</span></td>
        <td><span class="${actualCls}">${fmtPct(r.actual_pnl_pct)}</span></td>
        <td><span class="${evalCls}">${fmtPct(r.evaluation_pct)}</span></td>
        <td>${r.buy_entries.length}</td>
        <td>${r.sell_entries.length}</td>
        <td>${r.latest_ratio.toFixed(2)}%</td>
      </tr>
    `;
  };
  tbody.innerHTML = data.map(rowFn).join("");
  makeSortable("trading-analysis-tbody", () => DATA.trading_analysis || [], rowFn);
}

function renderFundCashCharts() {
  const series = DATA.fund_cash_series || [];
  if (series.length === 0) return;

  const labels = series.map(s => s.date);
  const fmtM = v => v == null ? null : Math.round(v / 1_000_000);

  const commonOpts = (yLabel, tickFn, tooltipFn) => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: tooltipFn } },
    },
    scales: {
      x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
      y: { title: { display: true, text: yLabel }, ticks: { font: { size: 10 }, callback: tickFn } },
    },
  });

  new Chart(document.getElementById("chart-cash"), {
    type: "line",
    data: { labels, datasets: [{ data: series.map(s => fmtM(s.cash)), borderColor: "#1565c0", backgroundColor: "rgba(21,101,192,0.08)", tension: 0.2, pointRadius: 3, fill: true, spanGaps: true }] },
    options: commonOpts("百万円", v => `¥${v.toLocaleString()}M`, ctx => `¥${ctx.parsed.y != null ? ctx.parsed.y.toLocaleString() : "—"}M`),
  });

  new Chart(document.getElementById("chart-nav"), {
    type: "line",
    data: { labels, datasets: [{ data: series.map(s => fmtM(s.nav)), borderColor: "#2e7d32", backgroundColor: "rgba(46,125,50,0.08)", tension: 0.2, pointRadius: 3, fill: true, spanGaps: true }] },
    options: commonOpts("百万円", v => `¥${v.toLocaleString()}M`, ctx => `¥${ctx.parsed.y != null ? ctx.parsed.y.toLocaleString() : "—"}M`),
  });

  new Chart(document.getElementById("chart-cash-ratio"), {
    type: "line",
    data: { labels, datasets: [{ data: series.map(s => s.cash_ratio), borderColor: "#e65100", backgroundColor: "rgba(230,81,0,0.08)", tension: 0.2, pointRadius: 3, fill: true, spanGaps: true }] },
    options: commonOpts("%", v => `${v}%`, ctx => `${ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) : "—"}%`),
  });
}

function renderSearch() {
  const input = document.getElementById("ticker-search");
  const suggestions = document.getElementById("search-suggestions");

  function getSuggestions(q) {
    if (!q) return [];
    const lq = q.toLowerCase();
    return (DATA.latest || []).filter(r =>
      r.ticker.startsWith(q.toUpperCase()) || r.name.toLowerCase().includes(lq)
    ).slice(0, 10);
  }

  function showSuggestions(items) {
    if (items.length === 0) { suggestions.innerHTML = ""; suggestions.style.display = "none"; return; }
    suggestions.style.display = "block";
    suggestions.innerHTML = items.map(r => `
      <div class="suggestion-item" data-ticker="${r.ticker}">
        <span class="suggestion-ticker">${r.ticker}</span>
        <span>${r.name}</span>
      </div>
    `).join("");
    suggestions.querySelectorAll(".suggestion-item").forEach(el => {
      el.addEventListener("click", () => {
        input.value = el.dataset.ticker;
        suggestions.style.display = "none";
        showTickerData(el.dataset.ticker);
      });
    });
  }

  input.addEventListener("input", () => showSuggestions(getSuggestions(input.value.trim())));

  input.addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    const q = input.value.trim();
    const matches = getSuggestions(q);
    const ticker = (matches.find(r => r.ticker === q.toUpperCase()) || matches[0] || {}).ticker;
    if (ticker) { suggestions.style.display = "none"; showTickerData(ticker); }
  });

  document.addEventListener("click", e => {
    if (!e.target.closest(".search-box")) suggestions.style.display = "none";
  });
}

function showTickerData(ticker) {
  const result = document.getElementById("search-result");
  const src = DATA.all_series || DATA.timeseries || [];
  const entry = src.find(t => t.ticker === ticker);
  if (!entry) {
    result.innerHTML = `<p class="empty" style="padding:12px">銘柄データが見つかりません: ${ticker}</p>`;
    return;
  }

  const allSeries = entry.series;
  const rows = allSeries.filter(s => s.shares != null);
  const hasPrice = rows.some(s => s.price != null);

  const priceData = DATA.price_data?.[ticker] || [];
  const priceLabels = priceData.map(d => d.date);
  const priceValues = priceData.map(d => d.close);

  const events = [];
  for (let i = 1; i < allSeries.length; i++) {
    const prev = allSeries[i - 1];
    const curr = allSeries[i];
    const ps = prev.shares, cs = curr.shares;
    if ((ps == null || ps === 0) && cs > 0) {
      events.push({ date: curr.date, type: 'new',      icon: 'N', color: '#2e7d32', delta: cs,    pct: null });
    } else if (ps > 0 && cs != null && cs > ps) {
      const d = cs - ps;
      events.push({ date: curr.date, type: 'buyup',    icon: '↑', color: '#1565c0', delta: d,     pct: d / ps * 100 });
    } else if (ps > 0 && cs != null && cs > 0 && cs < ps) {
      const d = cs - ps;
      events.push({ date: curr.date, type: 'sell',     icon: '↓', color: '#e65100', delta: d,     pct: d / ps * 100 });
    } else if (ps > 0 && (cs == null || cs === 0)) {
      events.push({ date: prev.date, type: 'fullsell', icon: '✕', color: '#c62828', delta: -ps,   pct: -100 });
    }
  }

  const bodyRows = rows.map((s, i) => {
    const prev = i > 0 ? rows[i - 1] : null;
    const dShares = (s.shares != null && prev?.shares != null) ? s.shares - prev.shares : null;
    const dRatio  = (s.ratio  != null && prev?.ratio  != null) ? s.ratio  - prev.ratio  : null;
    const cls = dShares == null ? "" : dShares > 0 ? "delta-pos" : dShares < 0 ? "delta-neg" : "";
    const fmtD = (v, dec) => v == null ? "—"
      : `<span class="${cls}">${v >= 0 ? "+" : ""}${dec === 0 ? v.toLocaleString() : v.toFixed(dec)}</span>`;
    return `<tr>
      <td>${s.date}</td>
      <td>${s.shares != null ? s.shares.toLocaleString() : "—"}</td>
      <td>${s.ratio != null ? s.ratio.toFixed(2) : "—"}</td>
      ${hasPrice ? `<td>${s.price != null ? "¥" + s.price.toLocaleString() : "—"}</td>` : ""}
      <td>${fmtD(dShares, 0)}</td>
      <td>${fmtD(dRatio, 2)}</td>
    </tr>`;
  }).join("");

  result.innerHTML = `
    <div style="margin-bottom:12px">
      <span class="ticker" style="font-size:1.1rem">${ticker}</span>
      <span style="margin-left:8px;font-size:1rem;color:#333">${entry.name}</span>
    </div>
    <div style="position:relative;height:260px;margin-bottom:44px">
      <canvas id="ticker-chart"></canvas>
    </div>
    <p style="font-size:10px;color:#aaa;margin-top:-36px;margin-bottom:16px;padding-left:4px">
      ※ 日付はデータ取得日（当営業日）。価格・株数はPCFファイルに基づく前営業日（N-1）時点の値です。
    </p>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>日付</th><th>保有株数</th><th>保有比率 (%)</th>
        ${hasPrice ? "<th>株価</th>" : ""}
        <th>前日比株数</th><th>前日比比率 (pp)</th>
      </tr></thead>
      <tbody>${bodyRows}</tbody>
    </table></div>`;

  const TYPE_LABEL = { new: '新規買い入れ', buyup: '買い増し', sell: '売却', fullsell: '全売却' };

  const tradeMarkerPlugin = {
    id: 'tradeMarkers',
    afterDraw(chart) {
      const ctx = chart.ctx;
      const xAxis = chart.scales.x;
      const yAxis = chart.scales.y;
      const bottomY = yAxis.bottom, topY = yAxis.top;
      events.forEach(ev => {
        let xIdx = priceLabels.indexOf(ev.date);
        if (xIdx < 0) {
          let closest = -1, minDiff = Infinity;
          priceLabels.forEach((lbl, i) => {
            const diff = Math.abs(new Date(lbl) - new Date(ev.date));
            if (diff < minDiff) { minDiff = diff; closest = i; }
          });
          if (minDiff <= 5 * 86400000) xIdx = closest;
        }
        if (xIdx < 0) return;
        const x = xAxis.getPixelForValue(xIdx);
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = ev.color + '88';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, topY); ctx.lineTo(x, bottomY); ctx.stroke();
        const iconY = bottomY + 20;
        ev.iconX = x; ev.iconY = iconY;
        ctx.setLineDash([]);
        ctx.fillStyle = ev.color;
        ctx.beginPath(); ctx.arc(x, iconY, 10, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(ev.icon, x, iconY);
        ctx.restore();
      });
    }
  };

  if (tickerChart) tickerChart.destroy();
  const canvas = document.getElementById("ticker-chart");
  tickerChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: priceLabels,
      datasets: [{
        label: `${ticker} ${entry.name}`,
        data: priceValues,
        borderColor: "#1565c0",
        backgroundColor: "rgba(21,101,192,0.08)",
        tension: 0.2,
        pointRadius: 3,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 40 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterBody(items) {
              if (!items.length) return [];
              const ev = events.find(e => e.date === items[0].label);
              if (!ev) return [];
              const eventPrice = priceData.find(d => d.date === ev.date)?.close || 0;
              const amount = Math.abs(ev.delta) * eventPrice;
              const sign = ev.delta >= 0 ? '+' : '';
              const pctStr = ev.pct != null ? ` (${ev.pct >= 0 ? '+' : ''}${ev.pct.toFixed(1)}%)` : '';
              return [
                `【${TYPE_LABEL[ev.type]}】`,
                `${sign}${ev.delta.toLocaleString()}株${pctStr}`,
                `株価: ¥${eventPrice.toLocaleString()}`,
                `売買金額: ¥${Math.round(amount).toLocaleString()}`,
              ];
            }
          }
        }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
        y: {
          title: { display: true, text: '株価（円）' },
          ticks: { callback: v => `¥${v.toLocaleString()}`, font: { size: 10 } }
        }
      }
    },
    plugins: [tradeMarkerPlugin]
  });

  const tooltip = document.getElementById("trade-tooltip");
  canvas.addEventListener('mousemove', e => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let found = false;
    events.forEach(ev => {
      if (ev.iconX == null) return;
      if (Math.sqrt((mx - ev.iconX) ** 2 + (my - ev.iconY) ** 2) < 12) {
        found = true;
        const eventPrice = priceData.find(d => d.date === ev.date)?.close || 0;
        const amount = Math.abs(ev.delta) * eventPrice;
        const sign = ev.delta >= 0 ? '+' : '';
        const pctStr = ev.pct != null ? ` (${ev.pct >= 0 ? '+' : ''}${ev.pct.toFixed(1)}%)` : '';
        tooltip.innerHTML = `📅 ${ev.date}<br>━━━━━━━━━━<br>${ev.icon} ${TYPE_LABEL[ev.type]}<br>${sign}${ev.delta.toLocaleString()}株${pctStr}<br>株価: ¥${eventPrice.toLocaleString()}<br>売買金額: ¥${Math.round(amount).toLocaleString()}`;
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 16) + 'px';
        tooltip.style.top = (e.clientY - 8) + 'px';
      }
    });
    if (!found) tooltip.style.display = 'none';
  });
  canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
}

load();
