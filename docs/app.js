/* orbital-watch website logic.
 *
 * No build step, no bundler -- plain script tags (Leaflet + satellite.js
 * from CDN, see index.html) so GitHub Pages can serve this directory as-is.
 *
 * Position tracking runs entirely in the browser: satellite.js does the
 * same SGP4 math our Python backend does, recomputed every second from the
 * TLE already in data.json. No live server needed for this part.
 */

const NASA_API_KEY = "DEMO_KEY"; // works out of the box, 30 req/hour --
// get a free personal key at https://api.nasa.gov and replace this if you
// hit that limit.

let map;
let marker;
let groundTrackLine;
let updateTimer;
let siteData;

function isoDateDaysAgo(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function initMap() {
  map = L.map("map", { worldCopyJump: true }).setView([0, 0], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 10,
  }).addTo(map);
  marker = L.circleMarker([0, 0], { radius: 6, color: "#58a6ff", fillOpacity: 0.9 }).addTo(map);
}

function satrecFor(sat) {
  if (!sat.line1 || !sat.line2) return null;
  return satellite.twoline2satrec(sat.line1, sat.line2);
}

function currentLatLon(satrec, date) {
  const positionAndVelocity = satellite.propagate(satrec, date);
  if (!positionAndVelocity.position) return null; // decayed/invalid element set
  const gmst = satellite.gstime(date);
  const geodetic = satellite.eciToGeodetic(positionAndVelocity.position, gmst);
  return {
    lat: satellite.degreesLat(geodetic.latitude),
    lon: satellite.degreesLong(geodetic.longitude),
  };
}

function drawGroundTrack(satrec) {
  if (groundTrackLine) map.removeLayer(groundTrackLine);
  // One full orbital period, sampled at ~100 points -- mean motion (rev/day)
  // tells us the period; satrec.no is radians/minute.
  const periodMinutes = (2 * Math.PI) / satrec.no;
  const points = [];
  const now = new Date();
  for (let i = 0; i <= 100; i++) {
    const t = new Date(now.getTime() + (i / 100) * periodMinutes * 60000);
    const pos = currentLatLon(satrec, t);
    if (pos) points.push([pos.lat, pos.lon]);
  }
  groundTrackLine = L.polyline(points, { color: "#58a6ff", weight: 1, opacity: 0.5, dashArray: "4 4" }).addTo(map);
}

function startTracking(sat) {
  if (updateTimer) clearInterval(updateTimer);
  const satrec = satrecFor(sat);
  if (!satrec) {
    marker.setLatLng([0, 0]);
    return;
  }

  const tick = () => {
    const pos = currentLatLon(satrec, new Date());
    if (pos) {
      marker.setLatLng([pos.lat, pos.lon]);
    }
  };

  tick();
  map.setView(marker.getLatLng(), map.getZoom());
  drawGroundTrack(satrec);
  updateTimer = setInterval(tick, 1000);
}

function renderStatus(sat) {
  const el = document.getElementById("status-content");
  const rows = [];

  rows.push(`<div class="status-row"><span class="label">NORAD ID</span><br>${sat.norad_id}</div>`);

  if (sat.tle_age_days !== null && sat.tle_age_days !== undefined) {
    // A negative age is real (if rare) live behavior, not a bug: CelesTrak
    // occasionally publishes a TLE whose fit epoch is slightly ahead of
    // fetch time -- a catalog/clock-skew artifact (confirmed live,
    // 2026-07-05, NORAD 25867/Chandra: -1.8 days). Spelled out instead of
    // shown as a bare "-1.8 day(s) old", which reads as broken.
    let ageText;
    let badge;
    if (sat.tle_age_days < 0) {
      ageText = `epoch ${Math.abs(sat.tle_age_days).toFixed(1)} day(s) ahead of fetch time`;
      badge = '<span class="badge badge-ok">fresh</span>';
    } else {
      const stale = sat.tle_age_days > 7;
      ageText = `${sat.tle_age_days.toFixed(1)} day(s) old`;
      badge = stale
        ? '<span class="badge badge-warn">STALE</span>'
        : '<span class="badge badge-ok">fresh</span>';
    }
    rows.push(
      `<div class="status-row"><span class="label">TLE age</span><br>${ageText} ${badge}</div>`
    );
  } else {
    rows.push('<div class="status-row"><span class="label">TLE age</span><br>not fetched yet</div>');
  }

  if (sat.latest_maneuver) {
    rows.push(
      `<div class="status-row"><span class="label">Latest maneuver</span><br>` +
        `<span class="badge badge-danger">MANEUVER</span> ${sat.latest_maneuver.reason} ` +
        `<br><span class="label">${sat.latest_maneuver.timestamp}</span></div>`
    );
  } else {
    rows.push('<div class="status-row"><span class="label">Maneuvers</span><br>None detected yet.</div>');
  }

  if (sat.satnogs_health) {
    const badge = sat.satnogs_health.is_degraded
      ? '<span class="badge badge-warn">DEGRADED</span>'
      : '<span class="badge badge-ok">healthy</span>';
    rows.push(`<div class="status-row"><span class="label">SatNOGS health</span><br>${badge} ${sat.satnogs_health.reason}</div>`);
  } else {
    rows.push('<div class="status-row"><span class="label">SatNOGS health</span><br>No data yet (run with --include-satnogs).</div>');
  }

  el.innerHTML = rows.join("");
}

function renderInstruments(sat) {
  const el = document.getElementById("instruments-content");
  const info = sat.instruments;

  if (!info) {
    el.innerHTML = '<div class="no-imagery">No instrument/mission info on file for this satellite yet.</div>';
    return;
  }

  const rows = [`<p>${info.description}</p>`];

  if (info.instruments && info.instruments.length > 0) {
    rows.push(
      `<div class="status-row"><span class="label">Instruments</span><br>${info.instruments.join(", ")}</div>`
    );
  }

  if (info.data_products && info.data_products.length > 0) {
    rows.push(
      `<div class="status-row"><span class="label">What it actually measures/does</span><br>${info.data_products.join(", ")}</div>`
    );
  }

  el.innerHTML = rows.join("");
}

function renderImagery(sat) {
  const el = document.getElementById("imagery-content");
  el.innerHTML = "Loading...";

  if (sat.imagery.kind === "gibs") {
    let date;
    if (sat.imagery.cadence === "annual") {
      date = `${new Date().getUTCFullYear() - 1}-01-01`;
    } else if (sat.imagery.cadence === "realtime") {
      date = isoDateDaysAgo(0); // today -- this product is near-real-time, not a daily composite
    } else {
      date = isoDateDaysAgo(1);
    }
    const url =
      "https://wvs.earthdata.nasa.gov/api/v1/snapshot" +
      `?REQUEST=GetSnapshot&LAYERS=${encodeURIComponent(sat.imagery.layer)}` +
      `&CRS=EPSG:4326&TIME=${date}&BBOX=-90,-180,90,180&FORMAT=image/jpeg&WIDTH=720&HEIGHT=360`;
    let cadenceNote;
    if (sat.imagery.cadence === "annual") {
      cadenceNote = "Annual composite (Landsat doesn't have a daily global GIBS layer) -- not today's image.";
    } else if (sat.imagery.cadence === "realtime") {
      cadenceNote = `Real global rain/snowfall-rate data, refreshed every 30 min (NASA GIBS/IMERG), ${date}.`;
    } else {
      cadenceNote = `Real imagery from this satellite's instrument, ${date} (NASA GIBS).`;
    }
    el.innerHTML = `<img src="${url}" alt="Satellite imagery"><div class="caption">${cadenceNote}</div>`;
    return;
  }

  if (sat.imagery.kind === "apod") {
    fetch(`https://api.nasa.gov/planetary/apod?api_key=${NASA_API_KEY}`)
      .then((r) => r.json())
      .then((apod) => {
        if (apod.media_type === "image") {
          el.innerHTML =
            `<img src="${apod.url}" alt="${apod.title}">` +
            `<div class="caption"><strong>${apod.title}</strong> (NASA Astronomy Picture of the Day, ${apod.date}) -- ` +
            `may or may not be from Hubble specifically.</div>`;
        } else {
          el.innerHTML = `<div class="no-imagery">Today's NASA APOD is a video, not an image: <a href="${apod.url}">${apod.title}</a></div>`;
        }
      })
      .catch(() => {
        el.innerHTML = '<div class="no-imagery">Could not load NASA APOD right now (rate limit or network issue).</div>';
      });
    return;
  }

  el.innerHTML = '<div class="no-imagery">No public imagery source available for this satellite.</div>';
}

// --- Rotating backdrop of real satellite-captured photos ---
// Sources (all real, none fabricated/stock):
//  - GOES-16/18 GeoColor: NOAA's CDN always serves the CURRENT full-disk
//    image at a fixed URL (confirmed real, refreshed ~every 10 min); each
//    rotation cache-busts the URL so the browser re-fetches whatever is
//    current instead of a stale cached copy.
//  - NASA EPIC (DSCOVR): real full-Earth photos, refreshed every 60-100 min;
//    fetched once per page load via EPIC's own JSON API, same graceful
//    .catch()-and-skip pattern already used for the APOD fetch below.
//  - NASA images-api.nasa.gov: real released Hubble/JWST photos.
// Rotating which of these real photos is DISPLAYED every 60s is honest;
// claiming each individual photo itself refreshes every 60s would not be
// (most of these sources don't update that fast -- see README).
const GOES_BACKDROPS = [
  { url: "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/FD/GEOCOLOR/1808x1808.jpg", caption: "GOES-16 (GOES-East) GeoColor, NOAA/NESDIS -- real near-real-time imagery, refreshed ~every 10 min" },
  { url: "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/1808x1808.jpg", caption: "GOES-18 (GOES-West) GeoColor, NOAA/NESDIS -- real near-real-time imagery, refreshed ~every 10 min" },
];

let backdropPool = [];
let backdropIndex = 0;
let backdropTimer;

function setBackdrop(entry, attemptsLeft) {
  if (!entry) return;
  // attemptsLeft bounds the onerror retry chain to one pass over the pool --
  // without this, a session where every source is unreachable (this site
  // blocked by a firewall/ad-blocker, or every CDN briefly down at once)
  // would retry forever in a tight loop instead of just leaving the plain
  // dark background.
  if (attemptsLeft === undefined) attemptsLeft = backdropPool.length;
  const img = new Image();
  img.onload = () => {
    document.getElementById("backdrop-image").style.backgroundImage = `url("${entry.url}")`;
    const captionEl = document.getElementById("backdrop-caption");
    captionEl.textContent = entry.caption;
    captionEl.classList.add("visible");
  };
  img.onerror = () => {
    if (attemptsLeft > 1 && backdropPool.length > 1) {
      backdropIndex = (backdropIndex + 1) % backdropPool.length;
      setBackdrop(backdropPool[backdropIndex], attemptsLeft - 1);
    }
  };
  img.src = entry.url;
}

function fetchEpicPhotos() {
  return fetch("https://epic.gsfc.nasa.gov/api/natural")
    .then((r) => r.json())
    .then((images) =>
      images.slice(0, 4).map((img) => {
        const [year, month, day] = img.date.split(" ")[0].split("-");
        return {
          url: `https://epic.gsfc.nasa.gov/archive/natural/${year}/${month}/${day}/png/${img.image}.png`,
          caption: `NASA EPIC (DSCOVR), ${img.date} -- real full-Earth photo from 1 million miles away`,
        };
      })
    )
    .catch(() => []); // EPIC unreachable/rate-limited -- just fewer real photos in the pool, not a crash
}

function fetchDeepSpacePhotos() {
  const queries = ["hubble nebula", "james webb space telescope"];
  return Promise.all(
    queries.map((q) =>
      fetch(`https://images-api.nasa.gov/search?q=${encodeURIComponent(q)}&media_type=image`)
        .then((r) => r.json())
        .then((result) => {
          const items = (result.collection && result.collection.items) || [];
          return items
            .slice(0, 3)
            .map((item) => ({
              url: item.links && item.links[0] && item.links[0].href,
              caption: `${(item.data && item.data[0] && item.data[0].title) || "NASA image"} (images.nasa.gov)`,
            }))
            .filter((entry) => entry.url);
        })
        .catch(() => [])
    )
  ).then((results) => results.flat());
}

function startBackdropRotation() {
  const cacheBust = (entry) => ({ ...entry, url: `${entry.url}?t=${Date.now()}` });

  Promise.all([fetchEpicPhotos(), fetchDeepSpacePhotos()]).then(([epic, deepSpace]) => {
    backdropPool = [...GOES_BACKDROPS, ...epic, ...deepSpace];
    if (backdropPool.length === 0) return; // all sources failed -- plain dark background, not broken
    setBackdrop(backdropPool[0]);
    if (backdropTimer) clearInterval(backdropTimer);
    backdropTimer = setInterval(() => {
      backdropIndex = (backdropIndex + 1) % backdropPool.length;
      const entry = backdropPool[backdropIndex];
      setBackdrop(GOES_BACKDROPS.includes(entry) ? cacheBust(entry) : entry);
    }, 60000);
  });
}

function selectSatellite(noradId) {
  const sat = siteData.satellites.find((s) => s.norad_id === noradId);
  if (!sat) return;
  startTracking(sat);
  renderStatus(sat);
  renderInstruments(sat);
  renderImagery(sat);
}

function populateDropdown() {
  const select = document.getElementById("satellite-select");
  select.innerHTML = "";

  const labels = siteData.category_labels || {};
  const byCategory = new Map();
  siteData.satellites.forEach((sat) => {
    const category = sat.category || "uncategorized";
    if (!byCategory.has(category)) byCategory.set(category, []);
    byCategory.get(category).push(sat);
  });

  // Grouped with <optgroup> instead of one flat 50-entry list -- with this
  // many satellites a flat dropdown is unusable, so people can jump
  // straight to "Earth Observation" or "Space Telescopes" etc. Category
  // order follows category_labels' key order (from the backend) rather
  // than whatever order satellites happen to appear in, so the groups show
  // up in a stable, sensible order every time.
  const orderedCategories = Object.keys(labels).filter((c) => byCategory.has(c));
  for (const category of byCategory.keys()) {
    if (!orderedCategories.includes(category)) orderedCategories.push(category);
  }

  for (const category of orderedCategories) {
    const group = document.createElement("optgroup");
    group.label = labels[category] || category;
    byCategory.get(category).forEach((sat) => {
      const option = document.createElement("option");
      option.value = sat.norad_id;
      option.textContent = `${sat.name} (${sat.norad_id})`;
      group.appendChild(option);
    });
    select.appendChild(group);
  }

  select.addEventListener("change", () => selectSatellite(Number(select.value)));
}

function loadData() {
  fetch("data.json")
    .then((r) => r.json())
    .then((data) => {
      siteData = data;
      document.getElementById("generated-at").textContent = `Data as of ${new Date(data.generated_at).toLocaleString()}`;
      populateDropdown();
      // Select whatever option the dropdown actually shows as chosen (its
      // first <option> in DOM/category order), not data.satellites[0] --
      // those two orderings differ (satellites[] is sorted by NORAD ID,
      // the dropdown is grouped by category), and picking the JSON array's
      // order here previously left the visible dropdown selection and the
      // rendered status/map for two different satellites.
      const select = document.getElementById("satellite-select");
      if (select.options.length > 0) {
        select.value = select.options[0].value;
        selectSatellite(Number(select.value));
      }
    })
    .catch((err) => {
      document.getElementById("status-content").innerHTML =
        '<div class="no-imagery">Could not load data.json -- has the scheduled workflow run yet?</div>';
      console.error(err);
    });
}

initMap();
loadData();
startBackdropRotation();
