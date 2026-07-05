/* orbital-watch website logic.
 *
 * No build step, no bundler -- plain script tags (satellite.js + globe.gl
 * from CDN, see index.html) so GitHub Pages can serve this directory as-is.
 *
 * Position tracking runs entirely in the browser: satellite.js does the
 * same SGP4 math our Python backend does, recomputed every second from the
 * TLE already in data.json. No live server needed for this part.
 */

const NASA_API_KEY = "DEMO_KEY"; // works out of the box, 30 req/hour --
// get a free personal key at https://api.nasa.gov and replace this if you
// hit that limit.

let globeInstance;
let updateTimer;
let siteData;
let historyData;

function isoDateDaysAgo(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

// --- 3D globe (replaces the old flat 2D map) ---
// globe.gl (built on three.js/WebGL) with real NASA/Copernicus-style Earth
// imagery textures shipped in the three-globe package itself -- not a
// screenshot or a fabricated image.
function initGlobe() {
  const container = document.getElementById("globe");
  globeInstance = new Globe(container)
    .width(container.clientWidth)
    .height(container.clientHeight)
    .globeImageUrl("https://cdn.jsdelivr.net/npm/three-globe@2.45.2/example/img/earth-night.jpg")
    .backgroundImageUrl("https://cdn.jsdelivr.net/npm/three-globe@2.45.2/example/img/night-sky.png")
    .backgroundColor("rgba(0,0,0,0)")
    .pointsData([])
    .pointLat("lat")
    .pointLng("lng")
    .pointAltitude(0.02)
    .pointRadius(0.7)
    .pointColor(() => "#58a6ff")
    // Pulsing ring around the marker so the current position is easy to
    // spot at a glance instead of a plain static dot.
    .ringsData([])
    .ringLat("lat")
    .ringLng("lng")
    .ringColor(() => (t) => `rgba(88, 166, 255, ${1 - t})`)
    .ringMaxRadius(4)
    .ringPropagationSpeed(3)
    .ringRepeatPeriod(1200)
    // Ground track: bright, dashed, and animated so it visibly "flows" in
    // the direction of travel instead of sitting as a static faint line.
    .pathsData([])
    .pathPoints("points")
    .pathPointLat((p) => p[0])
    .pathPointLng((p) => p[1])
    .pathColor(() => ["#58a6ff", "rgba(88, 166, 255, 0.15)"])
    .pathDashLength(0.06)
    .pathDashGap(0.03)
    .pathDashAnimateTime(6000)
    .pathStroke(1.5)
    .pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 0);

  // NOTE: autoRotate is deliberately left off. It rotates the camera every
  // frame regardless of what pointOfView() last set, so it was silently
  // undoing the "center on the tracked satellite" call in startTracking()
  // a moment after every selection -- the marker would drift away from the
  // middle of the view within a second or two of loading. Instead the
  // camera now follows the satellite continuously (see startTracking()).

  // globe.gl reads the container's size when it's constructed -- if the
  // layout hasn't fully settled yet (fonts/CSS still applying), the canvas
  // can end up the wrong size and the globe renders small/off-center
  // inside its box ("showing on the right side", not centered). Re-measure
  // once after the browser's next paint, and on every resize after that.
  requestAnimationFrame(() => {
    globeInstance.width(container.clientWidth).height(container.clientHeight);
  });
  window.addEventListener("resize", () => {
    globeInstance.width(container.clientWidth).height(container.clientHeight);
  });
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
    lng: satellite.degreesLong(geodetic.longitude),
  };
}

function groundTrackPoints(satrec) {
  // One full orbital period, sampled at ~100 points -- mean motion (rev/day)
  // tells us the period; satrec.no is radians/minute.
  const periodMinutes = (2 * Math.PI) / satrec.no;
  const now = new Date();
  const points = [];
  for (let i = 0; i <= 100; i++) {
    const t = new Date(now.getTime() + (i / 100) * periodMinutes * 60000);
    const pos = currentLatLon(satrec, t);
    if (pos) points.push([pos.lat, pos.lng]);
  }
  return points;
}

function startTracking(sat) {
  if (updateTimer) clearInterval(updateTimer);
  const satrec = satrecFor(sat);
  if (!satrec) {
    globeInstance.pointsData([]).ringsData([]).pathsData([]);
    return;
  }

  // Camera continuously follows the satellite's live position (a "chase
  // cam") instead of a one-time center -- a real satellite moves fast
  // enough (ISS crosses the globe in ~90 minutes) that centering only once,
  // on selection, would drift out of view again within a minute or two.
  // The first call also sets the zoom level (altitude); every call after
  // that omits altitude so a manual zoom/drag by the user is preserved
  // instead of being reset every tick.
  let zoomed = false;
  const tick = () => {
    const pos = currentLatLon(satrec, new Date());
    if (!pos) return;
    globeInstance.pointsData([pos]).ringsData([pos]);
    if (!zoomed) {
      globeInstance.pointOfView({ lat: pos.lat, lng: pos.lng, altitude: 2.2 }, 1000);
      zoomed = true;
    } else {
      globeInstance.pointOfView({ lat: pos.lat, lng: pos.lng }, 800);
    }
  };

  tick();
  globeInstance.pathsData([{ points: groundTrackPoints(satrec) }]);
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

  // Honest update-cadence line: this site's own check cadence is a fixed,
  // real fact (the GitHub Actions schedule); the satellite's OWN tracking
  // data doesn't refresh on a single fixed schedule across all 52 objects
  // (it varies a lot -- a Starlink vs. a GPS satellite), so that part
  // points at the real live number already shown above rather than
  // quoting one made-up cadence for everything.
  let updateNote = "This site checks for new data automatically every hour.";
  if (sat.tle_age_days !== null && sat.tle_age_days !== undefined) {
    updateNote += sat.tle_age_days < 0
      ? " This satellite's own tracking data (TLE) is current -- see \"TLE age\" above."
      : ` This satellite's own tracking data (TLE) was last updated ${sat.tle_age_days.toFixed(1)} day(s) ago (see "TLE age" above) -- how often NORAD republishes it varies a lot by object.`;
  }
  rows.push(`<div class="status-row"><span class="label">How often this updates</span><br>${updateNote}</div>`);

  el.innerHTML = rows.join("");
}

function gibsImageUrl(option) {
  let date;
  if (option.cadence === "annual") {
    date = `${new Date().getUTCFullYear() - 1}-01-01`;
  } else if (option.cadence === "realtime") {
    date = isoDateDaysAgo(0); // today -- this product is near-real-time, not a daily composite
  } else {
    date = isoDateDaysAgo(1);
  }
  const url =
    "https://wvs.earthdata.nasa.gov/api/v1/snapshot" +
    `?REQUEST=GetSnapshot&LAYERS=${encodeURIComponent(option.layer)}` +
    `&CRS=EPSG:4326&TIME=${date}&BBOX=-90,-180,90,180&FORMAT=image/jpeg&WIDTH=720&HEIGHT=360`;
  let cadenceNote;
  if (option.cadence === "annual") {
    cadenceNote = `Annual "${option.label}" composite (Landsat doesn't have a daily global GIBS layer) -- not today's image.`;
  } else if (option.cadence === "realtime") {
    cadenceNote = `Real "${option.label}" data, refreshed every 30 min (NASA GIBS/IMERG), ${date}.`;
  } else {
    cadenceNote = `Real "${option.label}" from this satellite's instrument, ${date} (NASA GIBS).`;
  }
  return { url, cadenceNote, date };
}

function renderGibsOption(option) {
  const el = document.getElementById("imagery-content");
  const { url, cadenceNote } = gibsImageUrl(option);
  const img = document.createElement("img");
  img.alt = option.label;
  img.src = url;
  const caption = document.createElement("div");
  caption.className = "caption";
  caption.textContent = cadenceNote;
  const body = el.querySelector(".imagery-body") || document.createElement("div");
  body.className = "imagery-body";
  body.innerHTML = "";
  body.appendChild(img);
  body.appendChild(caption);
  if (!el.contains(body)) el.appendChild(body);
}

function renderImagery(sat) {
  const el = document.getElementById("imagery-content");
  el.innerHTML = "Loading...";

  if (sat.imagery.kind === "gibs") {
    const options = sat.imagery.options;
    el.innerHTML = "";

    // Multiple real options (e.g. true-color vs. active-fire detection) get
    // a small switcher instead of silently picking one for the visitor.
    if (options.length > 1) {
      const switcher = document.createElement("div");
      switcher.className = "imagery-switcher";
      options.forEach((option, i) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = option.label;
        if (i === 0) btn.classList.add("active");
        btn.addEventListener("click", () => {
          switcher.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          renderGibsOption(option);
        });
        switcher.appendChild(btn);
      });
      el.appendChild(switcher);
    }

    renderGibsOption(options[0]);
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

function renderCollisionRisk(sat) {
  const el = document.getElementById("collision-content");
  if (!sat.conjunctions || sat.conjunctions.length === 0) {
    el.innerHTML = '<div class="no-imagery">No close approaches involving this satellite in the current CelesTrak SOCRATES run.</div>';
    return;
  }

  const rows = sat.conjunctions.map((c) => `
    <div class="status-row">
      <span class="badge badge-warn">CLOSE APPROACH</span> with <strong>${c.other_name}</strong> (NORAD ${c.other_norad_id})
      <br><span class="label">Time of closest approach: ${c.time_of_closest_approach}</span>
      <br><span class="label">Miss distance: ${c.min_range_km.toFixed(2)} km, max probability: ${c.max_probability}</span>
    </div>
  `);
  el.innerHTML = rows.join("");
}

function renderCrew(sat) {
  const panel = document.getElementById("crew-panel");
  const el = document.getElementById("crew-content");

  if (!sat.crew_aboard) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  if (sat.crew_aboard.length === 0) {
    el.innerHTML = '<div class="no-imagery">No crew data yet (run with --include-crew).</div>';
    return;
  }

  el.innerHTML = `<p>${sat.crew_aboard.length} real astronaut(s)/taikonaut(s) currently aboard, per Open Notify:</p>
    <ul>${sat.crew_aboard.map((name) => `<li>${name}</li>`).join("")}</ul>`;
}

function renderAchievement(sat) {
  const panel = document.getElementById("achievement-panel");
  const el = document.getElementById("achievement-content");

  // Only shown for satellites with a real, individually-verified milestone
  // (see achievements.json) -- most of the 52 tracked objects (an
  // individual Starlink, a GPS satellite) don't have one of their own, and
  // the panel just stays hidden rather than inventing something for them.
  if (!sat.achievement) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  el.innerHTML = `
    <p class="achievement-headline">${sat.achievement.headline}</p>
    <p class="achievement-detail">${sat.achievement.detail}</p>
  `;
}

function renderDeepSpaceProbes() {
  const panel = document.getElementById("deep-space-panel");
  const el = document.getElementById("deep-space-content");
  const probes = siteData.deep_space_probes || [];

  if (probes.length === 0) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  el.innerHTML = probes.map((p) => `
    <div class="probe-card">
      <h3>${p.name}</h3>
      <div class="probe-stat"><span class="label">Distance from Earth</span><br>
        ${p.distance_from_earth_au.toFixed(2)} AU (${(p.distance_from_earth_km / 1e9).toFixed(2)} billion km)</div>
      <div class="probe-stat"><span class="label">Current speed relative to Earth</span><br>
        ${p.speed_km_s.toFixed(2)} km/s</div>
      <div class="probe-stat"><span class="label">Launched</span><br>${p.launched}</div>
      <div class="probe-milestone">${p.milestone}</div>
    </div>
  `).join("");
}

function renderVolcanoStatus(sat) {
  const panel = document.getElementById("volcano-panel");
  const el = document.getElementById("volcano-content");

  // Only shown for the real thermal-imaging Earth observation satellites
  // (Terra/Aqua/Suomi NPP/NOAA-20 -- see site_data.py) -- USGS's feed
  // itself is US-only and isn't something this satellite's own processing
  // produced, so this is framed as real-world context, not a per-satellite
  // detection log.
  if (!sat.volcano_alerts) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  if (sat.volcano_alerts.length === 0) {
    el.innerHTML = '<div class="no-imagery">No US volcano currently above normal status, per USGS.</div>';
    return;
  }

  const colorToBadge = { RED: "badge-danger", ORANGE: "badge-warn", YELLOW: "badge-warn", GREEN: "badge-ok" };
  const rows = sat.volcano_alerts.map((v) => `
    <div class="status-row">
      <span class="badge ${colorToBadge[v.color_code] || "badge-warn"}">${v.alert_level}</span>
      <strong>${v.volcano_name}</strong> (${v.observatory})
      <br><span class="label">As of ${v.sent_utc} UTC -- <a href="${v.notice_url}">USGS notice</a></span>
    </div>
  `);
  el.innerHTML = `
    <p class="deep-space-note">Real-time USGS alert status, US volcanoes only -- this is the kind of thing thermal-imaging
    satellites like this one help monitor, not something computed by this site itself.</p>
    ${rows.join("")}
  `;
}

// Fetched client-side, live, at the moment a precipitation-watch satellite
// is selected -- NOT computed server-side and baked into data.json, because
// the satellite keeps moving (GPM orbits Earth roughly every 93 minutes),
// so a forecast for "wherever it was when the hourly pipeline last ran"
// would already be for the wrong place by the time someone loads the page.
// Open-Meteo is a real, free, keyless forecast API -- this is a genuine
// short-term weather-model forecast for the ground point below the
// satellite right now, not something the satellite itself measured (that's
// what the Imagery panel's real-time GPM rain-rate layer is for).
function renderPrecipitationForecast(sat) {
  const panel = document.getElementById("precipitation-panel");
  const el = document.getElementById("precipitation-content");

  if (sat.category !== "precipitation_watch") {
    panel.hidden = true;
    return;
  }

  const satrec = satrecFor(sat);
  const pos = satrec ? currentLatLon(satrec, new Date()) : null;
  if (!pos) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  el.innerHTML = "Loading ground forecast from Open-Meteo...";

  fetch(`https://api.open-meteo.com/v1/forecast?latitude=${pos.lat.toFixed(2)}&longitude=${pos.lng.toFixed(2)}&hourly=precipitation,snowfall&forecast_days=1&timezone=UTC`)
    .then((r) => r.json())
    .then((data) => {
      const times = data.hourly.time;
      const precip = data.hourly.precipitation;
      const snow = data.hourly.snowfall;
      const nowHour = new Date().getUTCHours();
      const startIdx = times.findIndex((t) => new Date(t).getUTCHours() === nowHour);
      const rows = times.slice(Math.max(startIdx, 0), Math.max(startIdx, 0) + 6).map((t, i) => {
        const idx = Math.max(startIdx, 0) + i;
        const hour = new Date(t).toISOString().slice(11, 16);
        return `<div class="status-row"><span class="label">${hour} UTC</span><br>` +
          `${precip[idx].toFixed(1)} mm rain, ${snow[idx].toFixed(1)} cm snow (forecast)</div>`;
      });
      el.innerHTML = `
        <p class="deep-space-note">Ground weather forecast (Open-Meteo) at this satellite's current position
        (${pos.lat.toFixed(1)}, ${pos.lng.toFixed(1)}) -- a weather-model forecast, not something the satellite
        itself measured.</p>
        ${rows.join("")}
      `;
    })
    .catch(() => {
      el.innerHTML = '<div class="no-imagery">Could not load Open-Meteo forecast right now.</div>';
    });
}

function renderHistory(sat) {
  const timeline = document.getElementById("history-timeline");
  const toggle = document.getElementById("history-toggle");
  timeline.hidden = true;
  timeline.innerHTML = "";
  toggle.textContent = "Show full history";
  toggle.disabled = false;

  toggle.onclick = () => {
    if (!timeline.hidden) {
      timeline.hidden = true;
      toggle.textContent = "Show full history";
      return;
    }

    const points = (historyData && historyData[String(sat.norad_id)]) || [];
    if (points.length === 0) {
      timeline.innerHTML = '<div class="no-imagery">No history yet -- this satellite hasn\'t been through enough scheduled runs.</div>';
    } else {
      // Most recent first, capped to the last 30 shown so the page stays
      // readable -- the underlying history.json already caps at 200.
      const rows = points.slice(-30).reverse().map((p) => {
        const residual = p.latest_residual_km_per_day !== null && p.latest_residual_km_per_day !== undefined
          ? `${p.latest_residual_km_per_day.toFixed(2)} km/day residual`
          : "no residual yet";
        const maneuverBit = p.new_maneuver_events.length > 0
          ? p.new_maneuver_events.map((e) => `<br><span class="badge badge-danger">MANEUVER</span> ${e.reason}`).join("")
          : "";
        return `<div class="status-row"><span class="label">${new Date(p.commit_time).toLocaleString()}</span><br>${residual}${maneuverBit}</div>`;
      });
      timeline.innerHTML = rows.join("");
    }
    timeline.hidden = false;
    toggle.textContent = "Hide full history";
  };
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
    // Start on a random photo, not always index 0 -- previously every page
    // load began on the same GOES-16 image no matter when you visited, and
    // only rotated from there, so "the picture that's already showing"
    // never reflected which minute you actually opened the site.
    backdropIndex = Math.floor(Math.random() * backdropPool.length);
    setBackdrop(backdropPool[backdropIndex]);
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
  renderCollisionRisk(sat);
  renderCrew(sat);
  renderHistory(sat);
  renderAchievement(sat);
  renderVolcanoStatus(sat);
  renderPrecipitationForecast(sat);
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

function loadHistory() {
  return fetch("history.json")
    .then((r) => r.json())
    .then((data) => {
      historyData = data;
    })
    .catch(() => {
      historyData = {}; // history.json missing/not generated yet -- "no history" is correct, not an error
    });
}

function loadData() {
  Promise.all([
    fetch("data.json").then((r) => r.json()),
    loadHistory(),
  ])
    .then(([data]) => {
      siteData = data;
      document.getElementById("generated-at").textContent = `Data as of ${new Date(data.generated_at).toLocaleString()}`;
      populateDropdown();
      renderDeepSpaceProbes();
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

initGlobe();
loadData();
startBackdropRotation();
