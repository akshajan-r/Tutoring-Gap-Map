"""A self-contained HTML preview of the dashboard (Leaflet map + SVG charts).

Tableau Public / Power BI remain the main dashboard (see dashboard/). This
preview is generated straight from the database, so you can sanity-check the
analysis, or share something interactive, before building the workbook.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .db import Database

SCHOOL_FIELDS = [
    "academic_year", "urn", "lineage_id", "school_name", "la_name", "region", "school_type",
    "latitude", "longitude", "imd_decile", "n_disadv", "pct_disadv", "att8_disadv",
    "att8_nondisadv", "gap_vs_national", "gap_within_school", "residual_z", "beating_odds",
]
LA_FIELDS = [
    "academic_year", "year_start", "la_code", "la_name", "region", "latitude", "longitude",
    "imd_score_avg", "n_schools", "n_disadv", "pct_disadv", "att8_disadv", "att8_nondisadv",
    "gap_within_la", "gap_vs_national", "scale_of_need", "rank_gap_vs_national",
    "n_las_in_year", "change_gap_vs_national", "prev_year", "trend",
]
BTO_FIELDS = [
    "lineage_id", "urn", "school_name", "la_name", "region", "school_type", "latitude",
    "longitude", "latest_year", "imd_decile", "pct_disadv", "n_disadv", "att8_disadv",
    "att8_disadv_expected", "residual_z", "years_in_model", "years_beating_odds", "evidence",
]


def _records(df, fields):
    df = df[[f for f in fields if f in df.columns]].copy()
    for c in df.select_dtypes("number").columns:
        df[c] = df[c].round(2)
    df = df.astype(object).where(df.notna(), None)
    return {"columns": list(df.columns), "rows": df.values.tolist()}


def write_dashboard(db: Database, path: Path, synthetic: bool = False,
                    downloads: list[tuple[str, str]] | None = None,
                    repo_url: str | None = None) -> Path:
    """downloads: (label, relative href) pairs listed in the footer (used by the site build)."""
    data = {
        "schools": _records(db.query("SELECT * FROM dash_schools"), SCHOOL_FIELDS),
        "las": _records(db.query("SELECT * FROM dash_local_authorities"), LA_FIELDS),
        "bto": _records(db.query("SELECT * FROM v_beating_the_odds"), BTO_FIELDS),
        "national": _records(db.query("SELECT * FROM v_national_trends ORDER BY year_start"),
                             ["academic_year", "year_start", "att8_disadv", "att8_nondisadv", "att8_gap"]),
        "synthetic": synthetic,
        "downloads": downloads or [],
        "repo_url": repo_url,
    }
    payload = json.dumps(data, separators=(",", ":"), default=lambda o: None if o is np.nan else str(o))
    html = TEMPLATE.replace("__DATA__", payload.replace("</", "<\\/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tutoring Gap Map</title>
<meta name="description" content="Where disadvantaged pupils in England fall furthest behind at GCSE, by local authority, and which schools serving deprived communities are beating the odds.">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root {
  color-scheme: light;
  --surface-0: #f5f4f1; --surface-1: #fcfcfb; --border: #e4e2dc; --grid: #ecebe7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #77756f;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
  --seq-1: #86b6ef; --seq-2: #5598e7; --seq-3: #2a78d6; --seq-4: #1c5cab; --seq-5: #0d366b;
  --warn-bg: #fff4d6; --warn-ink: #6b4a00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --border: #2f2f2c; --grid: #2a2a28;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #9a998f;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --warn-bg: #3a2e0d; --warn-ink: #ffd98a;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --border: #2f2f2c; --grid: #2a2a28;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #9a998f;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  --warn-bg: #3a2e0d; --warn-ink: #ffd98a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 0 0 2px; }
.sub { color: var(--text-secondary); margin: 0 0 16px; max-width: 75ch; }
.note { color: var(--text-muted); font-size: 12px; margin: 2px 0 10px; }
.banner { background: var(--warn-bg); color: var(--warn-ink); border-radius: 8px;
  padding: 10px 14px; margin-bottom: 16px; font-weight: 600; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 16px; }
.filters label { display: flex; flex-direction: column; font-size: 12px; color: var(--text-secondary); gap: 4px; }
select { font: inherit; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--surface-1); color: var(--text-primary); min-width: 150px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile, .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .k { font-size: 12px; color: var(--text-secondary); }
.tile .v { font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; }
.tile .d { font-size: 12px; color: var(--text-muted); }
.grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; }
@media (max-width: 900px) { .grid { grid-template-columns: minmax(0, 1fr); } }
#map { height: 520px; border-radius: 8px; z-index: 0; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--text-secondary); margin-top: 8px; align-items: center; }
.sw { display: inline-block; width: 14px; height: 10px; border-radius: 2px; vertical-align: middle; margin-right: 4px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle; margin-right: 4px; }
svg text { fill: var(--text-secondary); font-size: 11px; }
svg .val { fill: var(--text-primary); }
.bar { fill: var(--series-1); }
.bar.sel { fill: var(--series-2); }
.hit { fill: transparent; cursor: pointer; }
.row-hover .bar { opacity: .85; }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,.15); display: none; z-index: 1000; max-width: 280px; }
.tip b { display: block; margin-bottom: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 600; position: sticky; top: 0; background: var(--surface-1); }
td.n, th.n { text-align: right; }
#bto td:first-child { min-width: 200px; }
.scroll { max-height: 420px; overflow: auto; }
.pill { font-size: 11px; padding: 1px 6px; border-radius: 10px; border: 1px solid var(--border); color: var(--text-secondary); white-space: nowrap; }
.section { margin-top: 16px; }
footer { margin-top: 24px; color: var(--text-secondary); font-size: 13px; }
footer h2 { color: var(--text-primary); margin-top: 16px; }
footer h2:first-child { margin-top: 0; }
footer ul { margin: 6px 0; padding-left: 18px; }
footer li { margin: 3px 0; }
a { color: var(--series-1); }
@media (max-width: 600px) { #map { height: 380px; } .tile .v { font-size: 22px; } }
.leaflet-tooltip { font: 12px/1.4 system-ui, sans-serif; }
</style>
</head>
<body>
<main>
  <div id="banner" class="banner" hidden>Synthetic sample data. These schools, areas and scores are made up and only show how the dashboard works.</div>
  <h1>Tutoring Gap Map: England</h1>
  <p class="sub">Where disadvantaged pupils fall furthest behind at GCSE, and which schools serving deprived communities are beating the odds.
    The gap is measured in Attainment 8 points (divide by 10 for grades per subject) against the national average for non-disadvantaged pupils.</p>

  <div class="filters">
    <label>Year <select id="f-year"></select></label>
    <label>Region <select id="f-region"></select></label>
    <label>School type <select id="f-type"></select></label>
    <label>Rank areas by <select id="f-measure">
      <option value="gap_vs_national">Gap vs national non-disadvantaged</option>
      <option value="gap_within_la">Gap within the area</option>
      <option value="scale_of_need">Scale of need (pupils x grades)</option>
    </select></label>
  </div>

  <div class="tiles" id="tiles"></div>

  <div class="grid">
    <div class="card">
      <h2>Gap by local authority</h2>
      <p class="note">Circle size = disadvantaged pupils; darker = bigger gap. Ringed green dots are beating-the-odds schools. Click an area to see its trend.</p>
      <div id="map"></div>
      <div class="legend" id="map-legend"></div>
    </div>
    <div class="card">
      <h2 id="rank-title">Largest gaps</h2>
      <p class="note" id="rank-note"></p>
      <div id="rank"></div>
    </div>
  </div>

  <div class="grid section">
    <div class="card">
      <h2>Beating the odds</h2>
      <p class="note">State mainstream schools in deprived areas (IMD decile 1-3 or 40%+ disadvantaged) whose disadvantaged pupils score well above what their deprivation predicts. Sorted by years beating the odds, then average size of the margin.</p>
      <div class="scroll"><table id="bto"></table></div>
    </div>
    <div class="card">
      <h2 id="trend-title">Gap over time</h2>
      <p class="note" id="trend-note">Gap vs national non-disadvantaged, Attainment 8 points.</p>
      <div id="trend"></div>
      <div class="legend" id="trend-legend"></div>
    </div>
  </div>
  <footer class="card section">
    <h2>Data</h2>
    <ul>
      <li>GCSE results: DfE school performance tables (key stage 4), state-funded mainstream schools.</li>
      <li>School locations and types: Get Information About Schools.</li>
      <li>Deprivation: English Indices of Deprivation (IMD), by neighbourhood (LSOA).</li>
      <li>All Crown copyright, used under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>.</li>
    </ul>
    <p id="downloads" hidden></p>
    <h2>Method and caveats</h2>
    <ul>
      <li>"Disadvantaged" = eligible for free school meals in the last 6 years, or looked after. Averages are weighted by pupil numbers; schools with suppressed figures are left out.</li>
      <li>Beating the odds: disadvantaged pupils' Attainment 8 compared with a regression on neighbourhood deprivation and the school's % disadvantaged. Listed schools score at least one standard deviation above it, are in IMD deciles 1-3 or 40%+ disadvantaged, and have 10+ disadvantaged pupils. It flags schools worth learning from; it doesn't prove what causes the result.</li>
      <li>No school results were published for 2019-20 or 2020-21, and 2021-22 grading was more generous, so compare gaps rather than raw scores across years.</li>
      <li>Area circles sit at the average location of each local authority's schools. The school type filter applies to the tiles and the beating-the-odds list; area figures cover all school types.</li>
    </ul>
    <p id="repo" hidden></p>
  </footer>
</main>
<div class="tip" id="tip"></div>

<script>
const DATA = __DATA__;
const T = (d) => d.rows.map(r => Object.fromEntries(d.columns.map((c, i) => [c, r[i]])));
const schools = T(DATA.schools), las = T(DATA.las), bto = T(DATA.bto), national = T(DATA.national);
if (DATA.synthetic) document.getElementById('banner').hidden = false;

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (v, d = 1) => v == null ? '–' : Number(v).toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: d});
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const uniq = (a) => [...new Set(a.filter(x => x != null))].sort();

if (DATA.downloads.length) {
  const el = document.getElementById('downloads');
  el.innerHTML = '<b>Download the data:</b> ' + DATA.downloads.map(([label, href]) => `<a href="${esc(href)}" download>${esc(label)}</a>`).join(' · ');
  el.hidden = false;
}
if (DATA.repo_url) {
  const el = document.getElementById('repo');
  el.innerHTML = `Code, SQL and full method: <a href="${esc(DATA.repo_url)}">${esc(DATA.repo_url.replace('https://', ''))}</a>`;
  el.hidden = false;
}

const years = uniq(las.map(d => d.academic_year));
if (years.some(y => y < '2022')) document.getElementById('trend-note').textContent +=
  ' No school tables for 2019-20 or 2020-21; 2021-22 grading was more generous.';
const state = { year: years[years.length - 1], region: 'All', type: 'All', measure: 'gap_vs_national', la: null };
const measureLabel = { gap_vs_national: 'Gap vs national', gap_within_la: 'Gap within area', scale_of_need: 'Scale of need' };

function fillSelect(id, values, all, value) {
  const el = document.getElementById(id);
  el.innerHTML = (all ? `<option>All</option>` : '') + values.map(v => `<option>${esc(v)}</option>`).join('');
  el.value = value;
  el.onchange = () => { state[id.slice(2)] = el.value; render(); };
}
fillSelect('f-year', years, false, state.year);
fillSelect('f-region', uniq(las.map(d => d.region)), true, 'All');
fillSelect('f-type', uniq(schools.map(d => d.school_type)), true, 'All');
document.getElementById('f-measure').onchange = (e) => { state.measure = e.target.value; render(); };

// Tooltip
const tip = document.getElementById('tip');
function showTip(e, html) { tip.innerHTML = html; tip.style.display = 'block'; moveTip(e); }
function moveTip(e) {
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
}
function hideTip() { tip.style.display = 'none'; }

// Map
const map = L.map('map', { scrollWheelZoom: false }).setView([52.8, -1.6], 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 14, attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);
const laLayer = L.layerGroup().addTo(map), btoLayer = L.layerGroup().addTo(map);
const SEQ = ['--seq-1', '--seq-2', '--seq-3', '--seq-4', '--seq-5'];

function quantileBreaks(values, k) {
  const v = values.filter(x => x != null).sort((a, b) => a - b);
  return Array.from({length: k - 1}, (_, i) => v[Math.floor((i + 1) * v.length / k)] ?? 0);
}
const binOf = (x, br) => br.findIndex(b => x < b) === -1 ? br.length : br.findIndex(b => x < b);

function laRows() {
  return las.filter(d => d.academic_year === state.year && (state.region === 'All' || d.region === state.region));
}
function schoolRows() {
  return schools.filter(d => d.academic_year === state.year
    && (state.region === 'All' || d.region === state.region)
    && (state.type === 'All' || d.school_type === state.type));
}

function renderTiles() {
  const n = national.find(d => d.academic_year === state.year) || {};
  const s = schoolRows().filter(d => d.att8_disadv != null);
  const wsum = s.reduce((a, d) => a + (d.n_disadv || 0), 0);
  const att8d = wsum ? s.reduce((a, d) => a + d.att8_disadv * (d.n_disadv || 0), 0) / wsum : null;
  const nBto = btoFiltered().filter(d => d.evidence.startsWith('Consistent')).length;
  const scope = state.region === 'All' && state.type === 'All' ? 'England' : 'Selection';
  document.getElementById('tiles').innerHTML = [
    ['Disadvantaged pupils, Attainment 8', fmt(att8d), `${scope}, ${state.year}`],
    ['Non-disadvantaged, national', fmt(n.att8_nondisadv), 'Benchmark for the gap'],
    ['Gap vs national', fmt(n.att8_nondisadv != null && att8d != null ? n.att8_nondisadv - att8d : null),
      `≈ ${fmt(n.att8_nondisadv != null && att8d != null ? (n.att8_nondisadv - att8d) / 10 : null)} grades per subject`],
    ['Schools beating the odds', nBto, 'Consistently (2+ years), in the current filter'],
  ].map(([k, v, d]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join('');
}

function renderMap() {
  laLayer.clearLayers(); btoLayer.clearLayers();
  const rows = laRows().filter(d => d.latitude != null);
  const m = state.measure;
  const br = quantileBreaks(rows.map(d => d[m]), 5);
  const maxN = Math.max(1, ...rows.map(d => d.n_disadv || 0));
  rows.forEach(d => {
    const col = d[m] == null ? css('--text-muted') : css(SEQ[binOf(d[m], br)]);
    const c = L.circleMarker([d.latitude, d.longitude], {
      radius: 5 + 18 * Math.sqrt((d.n_disadv || 0) / maxN), color: '#ffffff', weight: 2,
      fillColor: col, fillOpacity: 0.9
    }).addTo(laLayer);
    c.bindTooltip(`<b>${esc(d.la_name)}</b>${esc(d.region)}<br>Gap vs national: ${fmt(d.gap_vs_national)}<br>
      Gap within area: ${fmt(d.gap_within_la)}<br>Disadvantaged Att8: ${fmt(d.att8_disadv)}<br>
      Disadvantaged pupils: ${fmt(d.n_disadv, 0)} (${fmt(d.pct_disadv, 0)}%)<br>Rank: ${d.rank_gap_vs_national} of ${d.n_las_in_year}`);
    c.on('click', () => { state.la = d.la_code; renderTrend(); renderRank(); });
  });
  btoFiltered().filter(d => d.evidence.startsWith('Consistent') && d.latitude != null).forEach(d => {
    L.circleMarker([d.latitude, d.longitude], { radius: 5, color: '#ffffff', weight: 2,
      fillColor: css('--series-3'), fillOpacity: 1 }).addTo(btoLayer)
      .bindTooltip(`<b>${esc(d.school_name)}</b>${esc(d.la_name)}<br>Disadvantaged Att8 ${fmt(d.att8_disadv)} vs ${fmt(d.att8_disadv_expected)} expected<br>Beat the odds ${d.years_beating_odds} of ${d.years_in_model} years`);
  });
  const lo = rows.map(d => d[m]).filter(x => x != null);
  const edges = [Math.min(...lo), ...br, Math.max(...lo)];
  document.getElementById('map-legend').innerHTML = `<span>${measureLabel[m]}:</span>` +
    SEQ.map((v, i) => `<span><span class="sw" style="background:${css(v)}"></span>${fmt(edges[i], m === 'scale_of_need' ? 0 : 1)}–${fmt(edges[i + 1], m === 'scale_of_need' ? 0 : 1)}</span>`).join('') +
    `<span><span class="dot" style="background:${css('--series-3')};box-shadow:0 0 0 2px #fff,0 0 0 3px ${css('--border')}"></span>Beating the odds</span>`;
}

function renderRank() {
  const m = state.measure;
  const rows = laRows().filter(d => d[m] != null).sort((a, b) => b[m] - a[m]).slice(0, 15);
  document.getElementById('rank-title').textContent = `Largest gaps: top ${rows.length} areas`;
  document.getElementById('rank-note').textContent = `${measureLabel[m]}, ${state.year}${state.region !== 'All' ? ', ' + state.region : ''}. Hover for details, click to see the trend.`;
  const el = document.getElementById('rank');
  const W = Math.max(300, el.clientWidth || 460), rowH = 24, lw = Math.min(140, W * 0.32), H = rows.length * rowH + 8;
  const max = Math.max(...rows.map(d => d[m]), 1);
  const x = (v) => lw + (W - lw - 48) * Math.max(0, v) / max;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Bar chart of the largest gaps">`;
  rows.forEach((d, i) => {
    const y = i * rowH + 4, sel = d.la_code === state.la;
    svg += `<g data-i="${i}"><text x="${lw - 8}" y="${y + 15}" text-anchor="end">${esc(d.la_name).slice(0, 22)}</text>
      <rect class="bar${sel ? ' sel' : ''}" x="${lw}" y="${y + 4}" width="${Math.max(2, x(d[m]) - lw)}" height="${rowH - 10}" rx="4"/>
      <text class="val" x="${x(d[m]) + 6}" y="${y + 15}">${fmt(d[m], m === 'scale_of_need' ? 0 : 1)}</text>
      <rect class="hit" x="0" y="${y}" width="${W}" height="${rowH}"/></g>`;
  });
  el.innerHTML = svg + '</svg>';
  el.querySelectorAll('g[data-i]').forEach(g => {
    const d = rows[+g.dataset.i];
    g.onmousemove = (e) => showTip(e, `<b>${esc(d.la_name)}</b>${esc(d.region)}<br>Gap vs national: ${fmt(d.gap_vs_national)}<br>Gap within area: ${fmt(d.gap_within_la)}<br>Scale of need: ${fmt(d.scale_of_need, 0)}<br>Change since ${esc(d.prev_year || '–')}: ${fmt(d.change_gap_vs_national)} ${d.trend ? '(' + d.trend + ')' : ''}`);
    g.onmouseleave = hideTip;
    g.onclick = () => { state.la = d.la_code; renderTrend(); renderRank(); };
  });
}

function btoFiltered() {
  return bto.filter(d => (state.region === 'All' || d.region === state.region)
    && (state.type === 'All' || d.school_type === state.type));
}
function renderBto() {
  const rows = btoFiltered().sort((a, b) => b.years_beating_odds - a.years_beating_odds || b.residual_z - a.residual_z);
  document.getElementById('bto').innerHTML = `<thead><tr><th>School</th><th>Area</th><th class="n">IMD decile</th>
    <th class="n">% disadv.</th><th class="n">Disadv. Att8</th><th class="n">Expected</th><th class="n">Years</th><th>Evidence</th></tr></thead><tbody>` +
    rows.map(d => `<tr><td>${esc(d.school_name)}<br><span class="note">${esc(d.school_type)}, URN ${d.urn}</span></td><td>${esc(d.la_name)}</td>
      <td class="n">${d.imd_decile ?? '–'}</td><td class="n">${fmt(d.pct_disadv, 0)}</td><td class="n">${fmt(d.att8_disadv)}</td>
      <td class="n">${fmt(d.att8_disadv_expected)}</td><td class="n">${d.years_beating_odds}/${d.years_in_model}</td>
      <td><span class="pill" title="${esc(d.evidence)}">${esc(d.evidence.replace(' (2+ years)', ''))}</span></td></tr>`).join('') +
    (rows.length ? '' : '<tr><td colspan="8">No schools in this filter.</td></tr>') + '</tbody>';
}

function renderTrend() {
  const sel = state.la ? las.filter(d => d.la_code === state.la).sort((a, b) => a.year_start - b.year_start) : [];
  // For England as a whole, "gap vs national non-disadvantaged" is just the national gap.
  const natLine = national.map(d => ({ y: d.academic_year, v: d.att8_gap }));
  const series = [{ name: 'England', key: '--series-1', pts: natLine }];
  if (sel.length) series.push({ name: sel[0].la_name, key: '--series-2', pts: sel.map(d => ({ y: d.academic_year, v: d.gap_vs_national })) });
  document.getElementById('trend-title').textContent = sel.length ? `Gap over time: ${sel[0].la_name} vs England` : 'Gap over time: England';
  const el = document.getElementById('trend');
  const W = Math.max(300, el.clientWidth || 460), H = 240, pl = 36, pr = 100, pt = 12, pb = 28;
  const xs = years, all = series.flatMap(s => s.pts.map(p => p.v)).filter(v => v != null);
  // Whole-number ticks: step chosen so there are at most 5 gridlines.
  const step = Math.max(1, Math.ceil((Math.max(...all) - Math.min(...all) + 2) / 4));
  const lo = Math.floor((Math.min(...all) - 1) / step) * step;
  const hi = Math.max(lo + step, Math.ceil((Math.max(...all) + 1) / step) * step);
  const X = (y) => pl + (W - pl - pr) * (xs.indexOf(y) / Math.max(1, xs.length - 1));
  const Y = (v) => pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo));
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Line chart of the gap over time">`;
  for (let v = lo; v <= hi + 1e-9; v += step) {
    svg += `<line x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('--grid')}"/>
      <text x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${fmt(v, 0)}</text>`;
  }
  // On narrow screens label every other year so the labels don't collide.
  const every = W < 420 ? 2 : 1;
  xs.forEach((y, i) => { if ((xs.length - 1 - i) % every === 0) svg += `<text x="${X(y)}" y="${H - 8}" text-anchor="middle">${y}</text>`; });
  series.forEach(s => {
    const pts = s.pts.filter(p => p.v != null && xs.includes(p.y));
    const col = css(s.key);
    svg += `<polyline fill="none" stroke="${col}" stroke-width="2" points="${pts.map(p => X(p.y) + ',' + Y(p.v)).join(' ')}"/>`;
    pts.forEach(p => svg += `<circle cx="${X(p.y)}" cy="${Y(p.v)}" r="4" fill="${col}" stroke="${css('--surface-1')}" stroke-width="2"/>`);
    const last = pts[pts.length - 1];
    if (last) svg += `<text class="val" x="${X(last.y) + 8}" y="${Y(last.v) + 4}">${esc(s.name).slice(0, 14)} ${fmt(last.v)}</text>`;
  });
  svg += `<line id="xh" y1="${pt}" y2="${H - pb}" stroke="${css('--text-muted')}" stroke-width="1" visibility="hidden"/>
    <rect class="hit" x="${pl}" y="${pt}" width="${W - pl - pr}" height="${H - pt - pb}"/></svg>`;
  el.innerHTML = svg;
  const hit = el.querySelector('rect.hit'), xh = el.querySelector('#xh'), svgEl = el.querySelector('svg');
  hit.onmousemove = (e) => {
    const r = svgEl.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
    const i = Math.round((px - pl) / ((W - pl - pr) / Math.max(1, xs.length - 1)));
    const y = xs[Math.max(0, Math.min(xs.length - 1, i))];
    xh.setAttribute('x1', X(y)); xh.setAttribute('x2', X(y)); xh.setAttribute('visibility', 'visible');
    showTip(e, `<b>${y}</b>` + series.map(s => { const p = s.pts.find(p => p.y === y);
      return `<span class="dot" style="background:${css(s.key)}"></span>${esc(s.name)}: ${fmt(p && p.v)}`; }).join('<br>'));
  };
  hit.onmouseleave = () => { xh.setAttribute('visibility', 'hidden'); hideTip(); };
  document.getElementById('trend-legend').innerHTML = series.map(s =>
    `<span><span class="sw" style="background:${css(s.key)}"></span>${esc(s.name)}</span>`).join('') +
    (sel.length ? '' : '<span>Click an area on the map or chart to compare it.</span>');
}

function render() { renderTiles(); renderMap(); renderRank(); renderBto(); renderTrend(); }
render();
// Frame the map on the areas that have data (works for any screen size).
const pts = las.filter(d => d.latitude != null).map(d => [d.latitude, d.longitude]);
if (pts.length) map.fitBounds(pts, { padding: [20, 20] });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
let resizeTimer;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { renderRank(); renderTrend(); }, 150); });
</script>
</body>
</html>
"""
