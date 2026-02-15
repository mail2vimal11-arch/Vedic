/**
 * Jyotish — Vedic Astrology Calculator
 * Frontend Application Logic
 *
 * Handles form submission, geocoding, geolocation,
 * result rendering, and interactive features.
 */

// ===================================================================
// COUNTRY DATA (name, UTC offset)
// ===================================================================
const COUNTRIES = [
    { name: "India", offset: 5.5 },
    { name: "United States", offset: -5 },
    { name: "United Kingdom", offset: 0 },
    { name: "Canada", offset: -5 },
    { name: "Australia", offset: 10 },
    { name: "Germany", offset: 1 },
    { name: "France", offset: 1 },
    { name: "Japan", offset: 9 },
    { name: "China", offset: 8 },
    { name: "Brazil", offset: -3 },
    { name: "South Africa", offset: 2 },
    { name: "Russia", offset: 3 },
    { name: "Mexico", offset: -6 },
    { name: "Indonesia", offset: 7 },
    { name: "South Korea", offset: 9 },
    { name: "Italy", offset: 1 },
    { name: "Spain", offset: 1 },
    { name: "Netherlands", offset: 1 },
    { name: "Saudi Arabia", offset: 3 },
    { name: "United Arab Emirates", offset: 4 },
    { name: "Turkey", offset: 3 },
    { name: "Thailand", offset: 7 },
    { name: "Singapore", offset: 8 },
    { name: "Malaysia", offset: 8 },
    { name: "Philippines", offset: 8 },
    { name: "Vietnam", offset: 7 },
    { name: "Egypt", offset: 2 },
    { name: "Nigeria", offset: 1 },
    { name: "Kenya", offset: 3 },
    { name: "Pakistan", offset: 5 },
    { name: "Bangladesh", offset: 6 },
    { name: "Sri Lanka", offset: 5.5 },
    { name: "Nepal", offset: 5.75 },
    { name: "Myanmar", offset: 6.5 },
    { name: "New Zealand", offset: 12 },
    { name: "Argentina", offset: -3 },
    { name: "Chile", offset: -3 },
    { name: "Colombia", offset: -5 },
    { name: "Peru", offset: -5 },
    { name: "Sweden", offset: 1 },
    { name: "Norway", offset: 1 },
    { name: "Denmark", offset: 1 },
    { name: "Finland", offset: 2 },
    { name: "Poland", offset: 1 },
    { name: "Portugal", offset: 0 },
    { name: "Greece", offset: 2 },
    { name: "Ireland", offset: 0 },
    { name: "Switzerland", offset: 1 },
    { name: "Austria", offset: 1 },
    { name: "Belgium", offset: 1 },
    { name: "Israel", offset: 2 },
    { name: "Iran", offset: 3.5 },
    { name: "Iraq", offset: 3 },
    { name: "Qatar", offset: 3 },
    { name: "Kuwait", offset: 3 },
    { name: "Oman", offset: 4 },
    { name: "Bahrain", offset: 3 },
    { name: "Jordan", offset: 2 },
    { name: "Lebanon", offset: 2 },
    { name: "Ghana", offset: 0 },
    { name: "Ethiopia", offset: 3 },
    { name: "Tanzania", offset: 3 },
    { name: "Uganda", offset: 3 },
    { name: "Morocco", offset: 1 },
    { name: "Tunisia", offset: 1 },
    { name: "Fiji", offset: 12 },
    { name: "Mauritius", offset: 4 },
    { name: "Jamaica", offset: -5 },
    { name: "Trinidad and Tobago", offset: -4 },
    { name: "Cambodia", offset: 7 },
    { name: "Laos", offset: 7 },
    { name: "Mongolia", offset: 8 },
    { name: "Afghanistan", offset: 4.5 },
    { name: "Bhutan", offset: 6 },
    { name: "Maldives", offset: 5 },
];

// Sort alphabetically
COUNTRIES.sort((a, b) => a.name.localeCompare(b.name));

// ===================================================================
// DOM REFERENCES
// ===================================================================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ===================================================================
// INITIALISATION
// ===================================================================
document.addEventListener("DOMContentLoaded", () => {
    populateCountries();
    bindEvents();
    setCurrentYear();
});

function setCurrentYear() {
    const el = $("#copyrightYear");
    if (el) el.textContent = new Date().getFullYear();
}

function populateCountries() {
    const select = $("#country");
    COUNTRIES.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.name;
        opt.textContent = c.name;
        opt.dataset.offset = c.offset;
        select.appendChild(opt);
    });
}

// ===================================================================
// EVENT BINDINGS
// ===================================================================
function bindEvents() {
    // Country change → auto-fill UTC offset
    $("#country").addEventListener("change", function () {
        const sel = this.options[this.selectedIndex];
        if (sel.dataset.offset !== undefined) {
            $("#utcOffset").value = sel.dataset.offset;
        }
    });

    // City lookup
    $("#lookupBtn").addEventListener("click", lookupCity);

    // Enter key on city triggers lookup
    $("#city").addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            lookupCity();
        }
    });

    // Geolocation
    $("#geolocateBtn").addEventListener("click", geolocate);

    // Form submission
    $("#birthForm").addEventListener("submit", handleSubmit);

    // Tabs
    $$(".tab").forEach((tab) => {
        tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });
}

// ===================================================================
// GEOCODING — Nominatim OpenStreetMap
// ===================================================================
async function lookupCity() {
    const city = $("#city").value.trim();
    const country = $("#country").value;

    if (!city) {
        showError("Please enter a city name.");
        return;
    }

    const btn = $("#lookupBtn");
    btn.disabled = true;
    btn.textContent = "...";

    try {
        const query = country ? `${city}, ${country}` : city;
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`;

        const resp = await fetch(url, {
            headers: { "Accept-Language": "en" },
        });
        const data = await resp.json();

        if (data && data.length > 0) {
            const result = data[0];
            $("#latitude").value = parseFloat(result.lat).toFixed(4);
            $("#longitude").value = parseFloat(result.lon).toFixed(4);
            hideError();
        } else {
            showError(`Could not find coordinates for "${city}". Please enter latitude/longitude manually.`);
        }
    } catch (err) {
        showError("Geocoding service unavailable. Please enter coordinates manually.");
    } finally {
        btn.disabled = false;
        btn.textContent = "\u{1F50D} Lookup";
    }
}

// ===================================================================
// GEOLOCATION (Browser)
// ===================================================================
function geolocate() {
    if (!navigator.geolocation) {
        showError("Geolocation is not supported by your browser.");
        return;
    }

    const btn = $("#geolocateBtn");
    btn.disabled = true;
    btn.textContent = "\u{1F4CD} Locating...";

    navigator.geolocation.getCurrentPosition(
        (pos) => {
            $("#latitude").value = pos.coords.latitude.toFixed(4);
            $("#longitude").value = pos.coords.longitude.toFixed(4);
            btn.disabled = false;
            btn.textContent = "\u{1F4CD} Use My Location";
            hideError();
        },
        (err) => {
            showError("Could not get your location. Please enter coordinates manually.");
            btn.disabled = false;
            btn.textContent = "\u{1F4CD} Use My Location";
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

// ===================================================================
// FORM SUBMISSION
// ===================================================================
async function handleSubmit(e) {
    e.preventDefault();

    // Validate required fields
    const birthDate = $("#birthDate").value;
    const birthTime = $("#birthTime").value;
    const lat = $("#latitude").value;
    const lon = $("#longitude").value;
    const utcOff = $("#utcOffset").value;

    if (!birthDate || !birthTime) {
        showError("Please enter both date and time of birth.");
        return;
    }
    if (!lat || !lon) {
        showError("Please enter birth coordinates (use city lookup or manual entry).");
        return;
    }
    if (utcOff === "") {
        showError("Please enter the UTC offset for the birth location.");
        return;
    }

    // Parse date/time
    const [year, month, day] = birthDate.split("-").map(Number);
    const timeParts = birthTime.split(":");
    const hour = parseInt(timeParts[0]);
    const minute = parseInt(timeParts[1]);
    const second = timeParts[2] ? parseInt(timeParts[2]) : 0;

    const payload = {
        name: $("#name").value.trim() || "Native",
        gender: $("#gender").value,
        year, month, day,
        hour, minute, second,
        latitude: parseFloat(lat),
        longitude: parseFloat(lon),
        utc_offset: parseFloat(utcOff),
        city: $("#city").value.trim(),
        country: $("#country").value,
    };

    // Show loading, hide results
    hideError();
    $("#loadingSection").style.display = "block";
    $("#resultsSection").style.display = "none";
    const submitBtn = $("#submitBtn");
    submitBtn.disabled = true;
    submitBtn.textContent = "Calculating...";

    try {
        const resp = await fetch("/api/chart", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(data.error || "Chart generation failed.");
        }

        renderResults(data);
    } catch (err) {
        showError(err.message || "An error occurred. Please try again.");
    } finally {
        $("#loadingSection").style.display = "none";
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate Birth Chart";
    }
}

// ===================================================================
// RENDER RESULTS
// ===================================================================
function renderResults(data) {
    renderSummary(data);
    renderChart(data);
    renderPlanets(data);
    renderDasha(data);
    renderCurrentDasha(data);

    $("#resultsSection").style.display = "block";
    switchTab("chartTab");

    // Scroll to results
    $("#resultsSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- Summary Banner ---
function renderSummary(data) {
    const b = data.birth_details;
    const c = data.chart;

    $("#summaryName").textContent = b.name;
    $("#summaryDateTime").textContent = `${b.date} at ${b.time}`;
    $("#summaryPlace").textContent = [b.city, b.country].filter(Boolean).join(", ") || `${b.latitude}, ${b.longitude}`;
    $("#summaryLagna").textContent = `${c.ascendant.sign} (${c.ascendant.sign_sanskrit}) ${c.ascendant.degrees}`;

    // Find Moon
    const moon = c.planets.find((p) => p.name === "Moon");
    if (moon) {
        $("#summaryMoonSign").textContent = `${moon.sign} (${moon.sign_sanskrit})`;
    }

    const n = data.nakshatra;
    $("#summaryNakshatra").textContent = `${n.name} (Pada ${n.pada}) — Lord: ${n.lord}`;
}

// --- Chart (SVG) ---
function renderChart(data) {
    const container = $("#chartContainer");
    if (data.svg_chart) {
        container.innerHTML = data.svg_chart;
    } else {
        container.innerHTML = '<p style="color:#999;padding:40px;">Chart SVG not available</p>';
    }

    $("#chartAyanamsa").textContent = data.chart.ayanamsa;
    $("#chartJD").textContent = data.chart.julian_day;
}

// --- Planets Table ---
function renderPlanets(data) {
    const tbody = $("#planetsTableBody");
    tbody.innerHTML = "";

    // Ascendant row
    const asc = data.chart.ascendant;
    const ascRow = document.createElement("tr");
    ascRow.classList.add("row-highlight");
    ascRow.innerHTML = `
        <td><strong>Ascendant (Lagna)</strong></td>
        <td>${asc.sign}</td>
        <td>${asc.sign_sanskrit}</td>
        <td>${asc.degrees}</td>
        <td>1</td>
        <td>${asc.lord}</td>
        <td>—</td>
    `;
    tbody.appendChild(ascRow);

    // Planet rows
    data.chart.planets.forEach((p) => {
        const tr = document.createElement("tr");
        const status = p.retrograde
            ? '<span class="tag-retro">R</span>'
            : '<span class="tag-direct">D</span>';
        tr.innerHTML = `
            <td><strong>${p.name}</strong></td>
            <td>${p.sign}</td>
            <td>${p.sign_sanskrit}</td>
            <td>${p.degrees}</td>
            <td>${p.house}</td>
            <td>${p.lord}</td>
            <td>${status}</td>
        `;
        tbody.appendChild(tr);
    });
}

// --- Dasha Timeline ---
function renderDasha(data) {
    const report = data.dasha_report;
    if (!report) return;

    // Balance info
    const bal = report.dasha_balance;
    const nak = report.nakshatra;
    const balBox = $("#dashaBalanceContent");
    balBox.innerHTML = `
        <p><strong>Birth Nakshatra:</strong> ${nak.name} (#${nak.number}, Pada ${nak.pada})</p>
        <p><strong>Nakshatra Lord:</strong> ${nak.lord}</p>
        <p><strong>Starting Dasha:</strong> ${bal.lord} — Balance: ${bal.balance_ymd.years}y ${bal.balance_ymd.months}m ${bal.balance_ymd.days}d</p>
    `;

    // Visual timeline bar
    const timelineEl = $("#dashaTimeline");
    timelineEl.innerHTML = "";
    const totalYears = report.maha_dashas.reduce((s, d) => s + d.duration_years, 0);

    // Find currently active maha dasha
    const activeMaha = data.current_dasha ? data.current_dasha.maha : null;

    report.maha_dashas.forEach((md) => {
        const pct = (md.duration_years / totalYears) * 100;
        const bar = document.createElement("div");
        bar.className = `dasha-bar dasha-${md.maha_dasha_lord.toLowerCase()}`;
        if (md.maha_dasha_lord === activeMaha) bar.classList.add("active-bar");
        bar.style.width = `${pct}%`;
        bar.textContent = md.maha_dasha_lord.substring(0, 3);
        bar.title = `${md.maha_dasha_lord}: ${md.start_date.substring(0, 10)} to ${md.end_date.substring(0, 10)} (${md.duration_ymd.years}y ${md.duration_ymd.months}m)`;
        bar.addEventListener("click", () => showAntardashas(md));
        timelineEl.appendChild(bar);
    });

    // Maha Dasha table
    const tbody = $("#dashaTableBody");
    tbody.innerHTML = "";

    report.maha_dashas.forEach((md, i) => {
        const tr = document.createElement("tr");
        if (md.maha_dasha_lord === activeMaha) tr.classList.add("row-highlight");

        const birthTag = md.is_birth_dasha ? ' <span class="tag-birth">Birth</span>' : "";
        const dur = `${md.duration_ymd.years}y ${md.duration_ymd.months}m ${md.duration_ymd.days}d`;

        tr.innerHTML = `
            <td>${i + 1}</td>
            <td><strong>${md.maha_dasha_lord}</strong>${birthTag}</td>
            <td>${formatDate(md.start_date)}</td>
            <td>${formatDate(md.end_date)}</td>
            <td>${dur}</td>
            <td><button class="btn-expand" data-idx="${i}">View Bhukti &#9660;</button></td>
        `;
        tbody.appendChild(tr);
    });

    // Bind expand buttons
    $$(".btn-expand").forEach((btn) => {
        btn.addEventListener("click", () => {
            const idx = parseInt(btn.dataset.idx);
            showAntardashas(report.maha_dashas[idx]);
        });
    });

    // Store report for later reference
    window._dashaReport = report;
}

function showAntardashas(mahaDasha) {
    const section = $("#antardashaSection");
    section.style.display = "block";

    $("#antardashaTitle").textContent = `Antardashas (Bhukti) within ${mahaDasha.maha_dasha_lord} Maha Dasha`;

    const tbody = $("#antardashaTableBody");
    tbody.innerHTML = "";

    mahaDasha.antardashas.forEach((ad, i) => {
        const tr = document.createElement("tr");
        const dur = `${ad.duration_ymd.years}y ${ad.duration_ymd.months}m ${ad.duration_ymd.days}d`;
        tr.innerHTML = `
            <td>${i + 1}</td>
            <td><strong>${ad.antar_dasha_lord}</strong></td>
            <td>${formatDate(ad.start_date)}</td>
            <td>${formatDate(ad.end_date)}</td>
            <td>${dur}</td>
        `;
        tbody.appendChild(tr);
    });

    section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// --- Current Dasha ---
function renderCurrentDasha(data) {
    const cd = data.current_dasha;
    const container = $("#currentDashaContent");

    const now = new Date();
    $("#currentDateLabel").textContent = `As of ${now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}`;

    if (!cd) {
        container.innerHTML = '<p style="padding:20px;color:#999;">Current dasha information not available for this birth date.</p>';
        return;
    }

    let html = `
        <div class="dasha-card dasha-card-maha">
            <div class="dasha-card-level">Maha Dasha</div>
            <div class="dasha-card-lord">${cd.maha}</div>
            <div class="dasha-card-dates">${cd.maha_start} — ${cd.maha_end}</div>
        </div>
        <div class="dasha-card dasha-card-antar">
            <div class="dasha-card-level">Antardasha (Bhukti)</div>
            <div class="dasha-card-lord">${cd.antar}</div>
            <div class="dasha-card-dates">${cd.antar_start} — ${cd.antar_end}</div>
        </div>
    `;

    if (cd.pratyantar) {
        html += `
            <div class="dasha-card dasha-card-pratyantar">
                <div class="dasha-card-level">Pratyantardasha</div>
                <div class="dasha-card-lord">${cd.pratyantar}</div>
                <div class="dasha-card-dates">${cd.pratyantar_start} — ${cd.pratyantar_end}</div>
            </div>
        `;
    }

    container.innerHTML = html;
}

// ===================================================================
// TABS
// ===================================================================
function switchTab(tabId) {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));

    const btn = document.querySelector(`.tab[data-tab="${tabId}"]`);
    const panel = $(`#${tabId}`);

    if (btn) btn.classList.add("active");
    if (panel) panel.classList.add("active");
}

// ===================================================================
// UTILITY FUNCTIONS
// ===================================================================
function showError(msg) {
    const banner = $("#errorBanner");
    const text = $("#errorText");
    text.textContent = msg;
    banner.style.display = "flex";
}

function hideError() {
    $("#errorBanner").style.display = "none";
}

function formatDate(dateStr) {
    if (!dateStr) return "—";
    // Input: "YYYY-MM-DD HH:MM:SS"
    const parts = dateStr.split(" ");
    const [y, m, d] = parts[0].split("-");
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${parseInt(d)}-${months[parseInt(m) - 1]}-${y}`;
}

// ===================================================================
// PRINT & DOWNLOAD
// ===================================================================
function printChart() {
    window.print();
}

function downloadSVG() {
    const svgEl = document.querySelector("#chartContainer svg");
    if (!svgEl) {
        alert("No chart available to download.");
        return;
    }

    const svgData = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "vedic_birth_chart.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
