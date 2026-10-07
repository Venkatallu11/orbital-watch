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
let siteData;
let historyData;
let achievementTimer;

// --- Time Machine simulation clock ---
// The globe is driven by this simulated clock instead of the wall clock.
// satellite.js's SGP4 propagator accepts ANY date, so advancing/rewinding
// simTime and re-propagating is genuine orbital mechanics -- the same math
// mission planners use -- not a fabricated animation. The only honest limit
// is that SGP4 accuracy degrades the further simTime gets from the TLE's
// epoch; that caveat is shown live in the panel (see updateCaveat()).
//
// `live` means "pinned to the present" (simTime = wall clock each frame).
// Any speed preset other than Live sets live=false and lets simTime run at
// timeScale x real time (negative = rewind). Live external-data panels
// (weather/fire/crew) are deliberately NOT driven by this clock -- there's
// no honest source for "the weather forecast 3 days ago at this point", so
// those always reflect the real present.
const simClock = {
  simTimeMs: Date.now(),
  timeScale: 1,
  playing: true,
  live: true,
  lastRealMs: null,
  lastTrackMs: 0,
  lastUiMs: 0,
  lastHashMs: 0,
  rafId: null,
  satrec: null,
  sat: null,
};

// Speed presets (multiplier on real time). Live is handled separately as a
// snap-to-now mode; these are the "run the simulation at N x" options.
const TIME_SPEEDS = [
  { label: "&#9664;&#9664; -1 day/s", scale: -86400 },
  { label: "&#9664; -1 hr/s", scale: -3600 },
  { label: "&#9664; -1 min/s", scale: -60 },
  { label: "1 min/s &#9654;", scale: 60 },
  { label: "1 hr/s &#9654;", scale: 3600 },
  { label: "1 day/s &#9654;&#9654;", scale: 86400 },
];

const SCRUB_RANGE_MIN = 60 * 24 * 60; // +/- 60 days, in minutes

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
    // Float the track just above the surface so it isn't z-fought/occluded by
    // the globe sphere, and give it a visible stroke.
    .pathPointAlt(0.01)
    .pathColor(() => ["#58a6ff", "rgba(88, 166, 255, 0.15)"])
    .pathDashLength(0.06)
    .pathDashGap(0.03)
    .pathDashAnimateTime(6000)
    .pathStroke(2.5)
    // CRITICAL: globe.gl animates a path "drawing on" over this duration on
    // every pathsData() change. The tracking loop rewrites pathsData several
    // times a second, so with the default ~1000ms the draw-on animation kept
    // restarting and the ground track never actually appeared -- only the
    // position marker showed. 0 = the path updates instantly and stays drawn.
    .pathTransitionDuration(0)
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

// Fuller instantaneous state -- position (lat/lng/altitude), speed, and the
// raw ECI vectors -- all straight from SGP4. Used by the tactical HUD and the
// nearby-contacts roster. Altitude is the real geodetic height (km); speed is
// the magnitude of the ECI velocity (km/s).
function currentState(satrec, date) {
  const pv = satellite.propagate(satrec, date);
  if (!pv.position) return null;
  const gmst = satellite.gstime(date);
  const geo = satellite.eciToGeodetic(pv.position, gmst);
  const v = pv.velocity;
  const speed = v ? Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) : null;
  return {
    lat: satellite.degreesLat(geo.latitude),
    lng: satellite.degreesLong(geo.longitude),
    altKm: geo.height,
    speedKmS: speed,
    eci: pv.position, // km, ECI frame -- directly comparable between objects
  };
}

function groundTrackPoints(satrec, fromDate) {
  // One full orbital period, sampled at ~100 points -- mean motion (rev/day)
  // tells us the period; satrec.no is radians/minute. The track is drawn
  // starting from `fromDate` (the simulated clock), so as you scrub/rewind
  // the ground track really is the orbit for that simulated moment.
  const periodMinutes = (2 * Math.PI) / satrec.no;
  const start = fromDate || new Date();
  const points = [];
  for (let i = 0; i <= 100; i++) {
    const t = new Date(start.getTime() + (i / 100) * periodMinutes * 60000);
    const pos = currentLatLon(satrec, t);
    if (pos) points.push([pos.lat, pos.lng]);
  }
  return points;
}

// TLE epoch as a JS Date, from satrec.jdsatepoch (Julian date). Used to tell
// the visitor honestly how far the simulated time is from the data the
// propagation is based on.
function tleEpochDate(satrec) {
  if (!satrec || !satrec.jdsatepoch) return null;
  return new Date((satrec.jdsatepoch - 2440587.5) * 86400000);
}

function startTracking(sat) {
  if (simClock.rafId) cancelAnimationFrame(simClock.rafId);
  simClock.rafId = null;
  simClock.lastRealMs = null;
  simClock.zoomed = false;
  simClock.lastContactsMs = 0; // refresh the nearby-contacts roster immediately

  const satrec = satrecFor(sat);
  simClock.sat = sat;
  simClock.satrec = satrec;

  // Deep-space probes (Voyager/Pioneer) have no Earth-orbit TLE, so there's
  // nothing for SGP4 to propagate -- the time machine, HUD and nearby-contacts
  // simply don't apply. Clear the globe and those panels rather than pretend.
  if (!satrec) {
    globeInstance.pointsData([]).ringsData([]).pathsData([]);
    setTimeMachineVisible(false);
    document.getElementById("contacts-panel").hidden = true;
    const hudReadout = document.getElementById("hud-readout");
    if (view.hud && hudReadout) {
      document.getElementById("hud-top").textContent = "NO ORBITAL TELEMETRY";
      hudReadout.innerHTML = '<div class="hud-line"><span>TYPE</span><b>deep-space probe (not Earth-orbiting)</b></div>';
    }
    return;
  }

  setTimeMachineVisible(true);
  renderTimeSpeeds();
  simClockFrame(performance.now());
}

// The single animation loop. requestAnimationFrame gives smooth motion even
// at high fast-forward rates; heavier work (recomputing the ground track,
// refreshing the readout, syncing the URL) is throttled below.
function simClockFrame(nowRealMs) {
  const satrec = simClock.satrec;
  if (!satrec) return;

  if (simClock.lastRealMs === null) simClock.lastRealMs = nowRealMs;
  const dtRealMs = nowRealMs - simClock.lastRealMs;
  simClock.lastRealMs = nowRealMs;

  if (simClock.live) {
    simClock.simTimeMs = Date.now();
  } else if (simClock.playing) {
    simClock.simTimeMs += simClock.timeScale * dtRealMs;
  }

  const simDate = new Date(simClock.simTimeMs);
  const pos = currentLatLon(satrec, simDate);
  if (pos) {
    globeInstance.pointsData([pos]).ringsData([pos]);
    // Cockpit mode drops the camera right down onto the satellite for an
    // orbital point-of-view ("ride the satellite"); normal mode keeps the
    // wider tracking altitude.
    const trackAlt = view.cockpit ? 0.42 : undefined;
    if (!simClock.zoomed) {
      globeInstance.pointOfView({ lat: pos.lat, lng: pos.lng, altitude: view.cockpit ? 0.42 : 2.2 }, 1000);
      simClock.zoomed = true;
      simClock.cockpitApplied = view.cockpit;
    } else if (view.cockpit !== simClock.cockpitApplied) {
      // mode just changed -> animate to the new altitude, then resume gentle follow
      globeInstance.pointOfView({ lat: pos.lat, lng: pos.lng, altitude: view.cockpit ? 0.42 : 2.2 }, 900);
      simClock.cockpitApplied = view.cockpit;
    } else {
      globeInstance.pointOfView(trackAlt === undefined
        ? { lat: pos.lat, lng: pos.lng }
        : { lat: pos.lat, lng: pos.lng, altitude: trackAlt }, 500);
    }
  }

  // Ground track: ~4x/sec is plenty and keeps 100 propagations off the
  // 60fps hot path.
  if (nowRealMs - simClock.lastTrackMs > 250) {
    globeInstance.pathsData([{ points: groundTrackPoints(satrec, simDate) }]);
    simClock.lastTrackMs = nowRealMs;
  }

  // Readout + caveat: ~4x/sec.
  if (nowRealMs - simClock.lastUiMs > 250) {
    updateTimeReadout(simDate, satrec);
    if (view.hud) updateHud(satrec, simDate);
    simClock.lastUiMs = nowRealMs;
  }

  // Nearby-contacts roster: real work (propagating the whole fleet), so only
  // ~ every 2.5s.
  if (nowRealMs - (simClock.lastContactsMs || 0) > 2500) {
    renderNearbyContacts(simClock.sat, simDate);
    simClock.lastContactsMs = nowRealMs;
  }

  // Keep the URL roughly in sync so a refresh restores the view; ~ every 3s
  // (using replaceState so we don't spam browser history).
  if (nowRealMs - simClock.lastHashMs > 3000) {
    updateUrlHash();
    simClock.lastHashMs = nowRealMs;
  }

  simClock.rafId = requestAnimationFrame(simClockFrame);
}

function setTimeMachineVisible(visible) {
  const panel = document.getElementById("time-machine-panel");
  if (panel) panel.hidden = !visible;
}

// Builds the speed-preset buttons + the Live button once per satellite.
function renderTimeSpeeds() {
  const wrap = document.getElementById("tm-speeds");
  if (!wrap) return;
  wrap.innerHTML = "";
  TIME_SPEEDS.forEach((preset) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tm-speed";
    btn.innerHTML = preset.label;
    btn.dataset.scale = String(preset.scale);
    btn.addEventListener("click", () => setSpeed(preset.scale));
    wrap.appendChild(btn);
  });
  highlightActiveSpeed();
}

function highlightActiveSpeed() {
  const wrap = document.getElementById("tm-speeds");
  if (wrap) {
    wrap.querySelectorAll(".tm-speed").forEach((b) => {
      const active = !simClock.live && simClock.playing && Number(b.dataset.scale) === simClock.timeScale;
      b.classList.toggle("active", active);
    });
  }
  const liveBtn = document.getElementById("tm-live");
  if (liveBtn) liveBtn.classList.toggle("active", simClock.live);
  const playBtn = document.getElementById("tm-playpause");
  if (playBtn) {
    playBtn.innerHTML = simClock.playing ? "&#10073;&#10073; Pause" : "&#9654; Play";
  }
}

function setSpeed(scale) {
  simClock.live = false;
  simClock.playing = true;
  simClock.timeScale = scale;
  highlightActiveSpeed();
  updateUrlHash();
}

function setLive() {
  simClock.live = true;
  simClock.playing = true;
  simClock.timeScale = 1;
  simClock.simTimeMs = Date.now();
  highlightActiveSpeed();
  updateUrlHash();
}

function togglePlay() {
  // Pausing a Live view drops out of live mode and freezes at the present
  // moment, so you can inspect the current position without it drifting.
  if (simClock.live) simClock.live = false;
  simClock.playing = !simClock.playing;
  highlightActiveSpeed();
  updateUrlHash();
}

function jumpBy(ms) {
  simClock.live = false;
  simClock.playing = false;
  simClock.simTimeMs += ms;
  highlightActiveSpeed();
  const simDate = new Date(simClock.simTimeMs);
  updateTimeReadout(simDate, simClock.satrec);
  if (simClock.satrec) {
    const pos = currentLatLon(simClock.satrec, simDate);
    if (pos) globeInstance.pointsData([pos]).ringsData([pos]);
    globeInstance.pathsData([{ points: groundTrackPoints(simClock.satrec, simDate) }]);
  }
  updateUrlHash();
}

function onScrub(minutesOffset) {
  simClock.live = false;
  simClock.playing = false;
  simClock.simTimeMs = Date.now() + minutesOffset * 60000;
  highlightActiveSpeed();
  const simDate = new Date(simClock.simTimeMs);
  updateTimeReadout(simDate, simClock.satrec);
  if (simClock.satrec) {
    const pos = currentLatLon(simClock.satrec, simDate);
    if (pos) globeInstance.pointsData([pos]).ringsData([pos]);
    globeInstance.pathsData([{ points: groundTrackPoints(simClock.satrec, simDate) }]);
  }
  updateUrlHash();
}

// Live clock readout + honest SGP4-accuracy caveat, both refreshed from the
// animation loop.
function updateTimeReadout(simDate, satrec) {
  const clockEl = document.getElementById("tm-clock");
  if (clockEl) {
    const nowMs = Date.now();
    const offsetMs = simClock.simTimeMs - nowMs;
    let rel;
    if (simClock.live) {
      rel = "live";
    } else if (Math.abs(offsetMs) < 60000) {
      rel = "now";
    } else {
      rel = humanizeOffset(offsetMs);
    }
    clockEl.innerHTML =
      `<span class="tm-clock-time">${simDate.toISOString().replace("T", " ").slice(0, 19)} UTC</span>` +
      `<span class="tm-clock-rel">${rel}</span>`;
  }

  // Keep the scrubber thumb roughly in step with the simulated time (unless
  // the user is actively dragging it).
  const scrub = document.getElementById("tm-scrub");
  if (scrub && document.activeElement !== scrub) {
    const minutesOffset = Math.round((simClock.simTimeMs - Date.now()) / 60000);
    scrub.value = String(Math.max(-SCRUB_RANGE_MIN, Math.min(SCRUB_RANGE_MIN, minutesOffset)));
  }

  updateCaveat(simDate, satrec);
}

function humanizeOffset(ms) {
  const sign = ms >= 0 ? "+" : "-";
  const abs = Math.abs(ms);
  const days = abs / 86400000;
  const hours = abs / 3600000;
  const mins = abs / 60000;
  if (days >= 1) return `${sign}${days.toFixed(1)} days from now`;
  if (hours >= 1) return `${sign}${hours.toFixed(1)} hours from now`;
  return `${sign}${mins.toFixed(0)} min from now`;
}

function updateCaveat(simDate, satrec) {
  const el = document.getElementById("tm-caveat");
  if (!el) return;
  const epoch = tleEpochDate(satrec);
  if (!epoch) {
    el.textContent = "";
    return;
  }
  const diffDays = Math.abs(simDate.getTime() - epoch.getTime()) / 86400000;
  let tier;
  let cls;
  if (diffDays < 3) {
    tier = "High confidence — within a few days of this satellite's orbital-data epoch.";
    cls = "badge-ok";
  } else if (diffDays < 14) {
    tier = "Reliable — SGP4 stays good for roughly two weeks from epoch.";
    cls = "badge-ok";
  } else if (diffDays < 60) {
    tier = "Approximate — position drifts noticeably this far from the orbital-data epoch.";
    cls = "badge-warn";
  } else {
    tier = "Rough / illustrative only — SGP4 isn't designed to propagate this far from epoch.";
    cls = "badge-danger";
  }
  el.innerHTML =
    `<span class="badge ${cls}">${diffDays.toFixed(1)} days from TLE epoch</span> ${tier} ` +
    `The globe uses real SGP4 propagation of this satellite's published orbit; live panels ` +
    `(weather, fire, crew) always reflect the present, not the simulated time.`;
}

// --- Shareable "lens" URL ---
// Encodes the current view (satellite + simulated time + speed + play state)
// in the URL hash, so a link reproduces the exact moment with no backend.
function updateUrlHash() {
  if (!simClock.sat) return;
  const params = new URLSearchParams();
  params.set("sat", String(simClock.sat.norad_id));
  if (simClock.live) {
    params.set("mode", "live");
  } else {
    params.set("t", String(Math.round(simClock.simTimeMs)));
    params.set("scale", String(simClock.timeScale));
    params.set("play", simClock.playing ? "1" : "0");
  }
  const newHash = "#" + params.toString();
  if (location.hash !== newHash) {
    history.replaceState(null, "", newHash);
  }
}

function readUrlHash() {
  if (!location.hash || location.hash.length < 2) return null;
  const params = new URLSearchParams(location.hash.slice(1));
  const sat = params.get("sat");
  if (!sat) return null;
  return {
    norad_id: Number(sat),
    mode: params.get("mode"),
    t: params.get("t") ? Number(params.get("t")) : null,
    scale: params.get("scale") ? Number(params.get("scale")) : null,
    play: params.get("play"),
  };
}

function applyLensState(state) {
  if (state.mode === "live" || state.t === null || Number.isNaN(state.t)) {
    setLive();
    return;
  }
  simClock.live = false;
  simClock.simTimeMs = state.t;
  simClock.timeScale = state.scale && !Number.isNaN(state.scale) ? state.scale : 1;
  simClock.playing = state.play !== "0";
  highlightActiveSpeed();
}

function shareLens() {
  updateUrlHash();
  const url = location.href;
  const statusEl = document.getElementById("tm-share-status");
  const done = (msg) => {
    if (statusEl) {
      statusEl.textContent = msg;
      setTimeout(() => { statusEl.textContent = ""; }, 4000);
    }
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(
      () => done("Link copied!"),
      () => done("Copy failed — URL is in the address bar.")
    );
  } else {
    done("URL is in the address bar — copy it to share this exact view.");
  }
}

function wireTimeMachineControls() {
  const playBtn = document.getElementById("tm-playpause");
  if (playBtn) playBtn.addEventListener("click", togglePlay);
  const liveBtn = document.getElementById("tm-live");
  if (liveBtn) liveBtn.addEventListener("click", setLive);
  const shareBtn = document.getElementById("tm-share");
  if (shareBtn) shareBtn.addEventListener("click", shareLens);
  document.querySelectorAll("[data-jump]").forEach((b) => {
    b.addEventListener("click", () => jumpBy(Number(b.dataset.jump)));
  });
  const scrub = document.getElementById("tm-scrub");
  if (scrub) {
    scrub.min = String(-SCRUB_RANGE_MIN);
    scrub.max = String(SCRUB_RANGE_MIN);
    scrub.step = "5";
    scrub.value = "0";
    scrub.addEventListener("input", () => onScrub(Number(scrub.value)));
  }
}

// --- Visible-pass prediction (Heavens-Above-style, 100% client-side) ---
// Given your location, work out when the selected satellite rises above your
// horizon, how high it gets, and -- crucially -- whether you can actually SEE
// it: a satellite is only visible when IT is sunlit while YOUR sky is dark.
// All of this is real orbital + solar geometry computed in the browser from
// the TLE already in data.json -- no API, no key, works offline.
const OBS_KEY = "ow_observer";
const DEG = Math.PI / 180;
const EARTH_R_KM = 6378.137;
let observer = loadObserver(); // {lat, lon, alt(km)} or null

function loadObserver() {
  try { const s = localStorage.getItem(OBS_KEY); return s ? JSON.parse(s) : null; } catch (e) { return null; }
}
function saveObserver(o) { try { localStorage.setItem(OBS_KEY, JSON.stringify(o)); } catch (e) { /* private mode */ } }

// Low-precision solar position in ECI (km) -- Astronomical Almanac's "low
// precision formulae for the Sun" (good to ~0.01°, far better than we need to
// decide sunlit-vs-shadow and day-vs-night).
function sunEci(date) {
  const jd = date.getTime() / 86400000 + 2440587.5;
  const n = jd - 2451545.0;
  const L = ((280.460 + 0.9856474 * n) % 360) * DEG;
  const g = ((357.528 + 0.9856003 * n) % 360) * DEG;
  const lambda = L + (1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * DEG;
  const eps = (23.439 - 0.0000004 * n) * DEG;
  const AU = 149597870.7;
  const r = (1.00014 - 0.01671 * Math.cos(g) - 0.00014 * Math.cos(2 * g)) * AU;
  return { x: r * Math.cos(lambda), y: r * Math.cos(eps) * Math.sin(lambda), z: r * Math.sin(eps) * Math.sin(lambda) };
}

// Is this ECI point in sunlight? Cylindrical-umbra test: sunlit unless it's on
// the far side of Earth from the Sun AND within one Earth radius of the
// Earth–Sun line (i.e. inside Earth's shadow cylinder).
function isSunlit(p, date) {
  const s = sunEci(date);
  const sr = Math.hypot(s.x, s.y, s.z);
  const sx = s.x / sr, sy = s.y / sr, sz = s.z / sr;
  const proj = p.x * sx + p.y * sy + p.z * sz;
  if (proj >= 0) return true;
  const perp = Math.hypot(p.x - proj * sx, p.y - proj * sy, p.z - proj * sz);
  return perp > EARTH_R_KM;
}

// Sun elevation at the observer (deg) -- below ~ -6° means the sky is dark
// enough to see a sunlit satellite.
function sunElevationDeg(obs, date) {
  const gmst = satellite.gstime(date);
  const ecf = satellite.eciToEcf(sunEci(date), gmst);
  const look = satellite.ecfToLookAngles(
    { longitude: obs.lon * DEG, latitude: obs.lat * DEG, height: (obs.alt || 0) },
    ecf
  );
  return look.elevation / DEG;
}

function azToCompass(az) {
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(((az % 360) / 22.5)) % 16];
}

// Find passes in the next `hours` hours with peak elevation above `minEl`.
function computePasses(satrec, obs, hours, minEl) {
  hours = hours || 48;
  minEl = minEl || 10;
  const obsGd = { longitude: obs.lon * DEG, latitude: obs.lat * DEG, height: (obs.alt || 0) };
  const stepMs = 30 * 1000;
  const start = Date.now();
  const end = start + hours * 3600 * 1000;
  const passes = [];
  let cur = null;
  const flush = () => {
    if (!cur) return;
    const peak = cur.samples.reduce((a, b) => (b.el > a.el ? b : a), cur.samples[0]);
    if (peak.el >= minEl) {
      const first = cur.samples[0], last = cur.samples[cur.samples.length - 1];
      passes.push({
        start: first.date, end: last.date, peakTime: peak.date,
        maxEl: peak.el, startAz: first.az, endAz: last.az,
        durationS: (last.date - first.date) / 1000,
        // visible = at some moment the satellite is sunlit while the observer's
        // sky is dark and the object is a reasonable height up.
        visible: cur.samples.some((s) => s.sunlit && s.sunEl < -6 && s.el > 5),
      });
    }
    cur = null;
  };
  for (let t = start; t <= end; t += stepMs) {
    const date = new Date(t);
    const pv = satellite.propagate(satrec, date);
    if (!pv.position) continue;
    const gmst = satellite.gstime(date);
    const look = satellite.ecfToLookAngles(obsGd, satellite.eciToEcf(pv.position, gmst));
    const el = look.elevation / DEG;
    if (el > 0) {
      if (!cur) cur = { samples: [] };
      cur.samples.push({
        date, el, az: look.azimuth / DEG,
        sunlit: isSunlit(pv.position, date),
        sunEl: sunElevationDeg(obs, date),
      });
    } else {
      flush();
    }
  }
  flush();
  return passes;
}

function renderPasses(sat) {
  const panel = document.getElementById("passes-panel");
  const el = document.getElementById("passes-content");
  if (!panel || !el) return;
  if (!sat || !sat.line1 || !sat.line2) { panel.hidden = true; return; }
  panel.hidden = false;

  if (!observer) {
    el.innerHTML = locationPromptHtml();
    wireLocationControls(sat);
    return;
  }

  el.innerHTML = `<p class="panel-note">Computing passes over ${observer.lat.toFixed(2)}°, ${observer.lon.toFixed(2)}° (next 48 h)…</p>`;
  // Defer the heavy loop one tick so the "computing…" note paints first.
  setTimeout(() => {
    if (!simClock.sat || simClock.sat.norad_id !== sat.norad_id) return; // selection moved on
    const satrec = satrecFor(sat);
    let passes = [];
    try { passes = computePasses(satrec, observer); } catch (e) { /* bad element set */ }
    el.innerHTML = renderPassListHtml(passes);
    wireLocationControls(sat);
  }, 0);
}

function renderPassListHtml(passes) {
  const loc = `<p class="panel-note">Your location: <strong>${observer.lat.toFixed(3)}°, ${observer.lon.toFixed(3)}°</strong> — ` +
    `<a href="#" id="passes-change">change</a>. Times are your local time; all computed in-browser from the TLE (real look-angle + solar geometry), not fetched.</p>`;

  if (passes.length === 0) {
    return loc + '<div class="no-imagery">No passes above 10° in the next 48 hours from your location (it may stay below your horizon, or this is a high/geostationary orbit).</div>';
  }

  // A pass longer than ~2 h isn't really a "pass" -- it's a high/GEO object
  // sitting in view. Label it honestly instead of as a fly-over.
  const rows = passes.slice(0, 12).map((p) => {
    const vis = p.visible
      ? '<span class="badge badge-ok">👁 VISIBLE</span>'
      : '<span class="badge badge-warn">radio/daylight only</span>';
    if (p.durationS > 7200) {
      return `<div class="status-row">${vis} <strong>Continuously in view</strong>` +
        `<br><span class="label">High/geostationary orbit — stays above your horizon (max el ${p.maxEl.toFixed(0)}°).</span></div>`;
    }
    const d = p.peakTime;
    const when = d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
    const dur = Math.round(p.durationS / 60);
    return `<div class="status-row">${vis} <strong>${when}</strong> (local)` +
      `<br><span class="label">max elevation ${p.maxEl.toFixed(0)}° · ${azToCompass(p.startAz)}→${azToCompass(p.endAz)} · ~${dur} min</span></div>`;
  }).join("");

  const visibleNote = passes.some((p) => p.visible)
    ? '<p class="panel-note">👁 marks passes you could actually <em>see</em> with the naked eye — the satellite is sunlit while your sky is dark.</p>'
    : '<p class="panel-note">None of these are naked-eye visible in this window (the satellite is in Earth\'s shadow, or your sky is still bright, when it passes).</p>';

  return loc + visibleNote + rows;
}

function locationPromptHtml() {
  return `<p class="panel-note">See when this satellite flies over <strong>you</strong> — and whether it'll be bright enough to spot. Set your location (kept only in your browser):</p>
    <div class="loc-controls">
      <button type="button" id="loc-geo">📍 Use my location</button>
      <span class="label">or enter it:</span>
      <input type="number" id="loc-lat" placeholder="lat" step="0.01" min="-90" max="90">
      <input type="number" id="loc-lon" placeholder="lon" step="0.01" min="-180" max="180">
      <button type="button" id="loc-set">Set</button>
    </div>
    <p class="panel-note" id="loc-status"></p>`;
}

function wireLocationControls(sat) {
  const geo = document.getElementById("loc-geo");
  if (geo) geo.addEventListener("click", () => {
    const status = document.getElementById("loc-status");
    if (!navigator.geolocation) { if (status) status.textContent = "Geolocation isn't available in this browser — enter coordinates manually."; return; }
    if (status) status.textContent = "Requesting your location…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        observer = { lat: pos.coords.latitude, lon: pos.coords.longitude, alt: (pos.coords.altitude || 0) / 1000 };
        saveObserver(observer);
        renderPasses(sat);
      },
      () => { if (status) status.textContent = "Couldn't get your location (permission denied?) — enter coordinates manually."; }
    );
  });
  const setBtn = document.getElementById("loc-set");
  if (setBtn) setBtn.addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("loc-lat").value);
    const lon = parseFloat(document.getElementById("loc-lon").value);
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      observer = { lat, lon, alt: 0 };
      saveObserver(observer);
      renderPasses(sat);
    } else {
      const status = document.getElementById("loc-status");
      if (status) status.textContent = "Please enter a valid latitude (−90…90) and longitude (−180…180).";
    }
  });
  const change = document.getElementById("passes-change");
  if (change) change.addEventListener("click", (e) => {
    e.preventDefault();
    observer = null;
    renderPasses(sat);
  });
}

// --- Cockpit controls: optics (sensor looks), tactical HUD, cockpit POV ---
// Inspired by "God's Eye View"-style situational displays, but driven entirely
// by our real SGP4 state and done client-side -- the optics are honest visual
// filters (clearly labelled), and the HUD numbers are the satellite's actual
// position/velocity/orbit, not mocked telemetry.
const view = { optics: "normal", hud: false, cockpit: false };

function applyOptics(mode) {
  view.optics = mode;
  const g = document.getElementById("globe");
  g.classList.remove("optic-normal", "optic-thermal", "optic-nvg", "optic-infrared", "optic-noir");
  g.classList.add("optic-" + mode);
  const sel = document.getElementById("optics-select");
  if (sel && sel.value !== mode) sel.value = mode;
}

function setHud(on) {
  view.hud = on;
  document.getElementById("hud-overlay").hidden = !on;
  document.getElementById("hud-toggle").classList.toggle("active", on);
  if (on && simClock.satrec) updateHud(simClock.satrec, new Date(simClock.simTimeMs));
}

function setCockpit(on) {
  view.cockpit = on;
  document.getElementById("cockpit-toggle").classList.toggle("active", on);
  simClock.cockpitApplied = !on; // force the loop to re-apply altitude next frame
}

function updateHud(satrec, date) {
  const topEl = document.getElementById("hud-top");
  const el = document.getElementById("hud-readout");
  if (!el) return;
  const st = currentState(satrec, date);
  if (!st) {
    if (topEl) topEl.textContent = "SIGNAL LOST";
    el.innerHTML = '<div class="hud-line"><span>STATUS</span><b>element set decayed/invalid</b></div>';
    return;
  }
  const inc = satrec.inclo * 180 / Math.PI;
  const periodMin = (2 * Math.PI) / satrec.no;
  const name = (simClock.sat && simClock.sat.name) || "TARGET";
  if (topEl) topEl.textContent = `TRACKING · ${name} · ${view.optics.toUpperCase()}`;
  const ns = st.lat >= 0 ? "N" : "S";
  const ew = st.lng >= 0 ? "E" : "W";
  // Is the satellite itself in sunlight or Earth's shadow right now? (Real
  // solar geometry -- the same test the visible-pass predictor uses.)
  const lit = isSunlit(st.eci, date);
  el.innerHTML = [
    ["NORAD", simClock.sat ? simClock.sat.norad_id : "—"],
    ["LAT", `${Math.abs(st.lat).toFixed(3)}° ${ns}`],
    ["LON", `${Math.abs(st.lng).toFixed(3)}° ${ew}`],
    ["ALT", `${st.altKm.toFixed(1)} km`],
    ["VEL", st.speedKmS ? `${st.speedKmS.toFixed(2)} km/s` : "—"],
    ["INC", `${inc.toFixed(2)}°`],
    ["PERIOD", `${periodMin.toFixed(1)} min`],
    ["LIGHT", lit ? "☀ sunlit" : "🌑 eclipse"],
  ].map(([k, v]) => `<div class="hud-line"><span>${k}</span><b>${v}</b></div>`).join("");
}

function wireViewControls() {
  const opt = document.getElementById("optics-select");
  if (opt) opt.addEventListener("change", () => applyOptics(opt.value));
  const hud = document.getElementById("hud-toggle");
  if (hud) hud.addEventListener("click", () => setHud(!view.hud));
  const cp = document.getElementById("cockpit-toggle");
  if (cp) cp.addEventListener("click", () => setCockpit(!view.cockpit));
  applyOptics("normal");
}

// Nearby contacts: the real closest objects in the fleet to the tracked
// satellite, by 3D distance between their SGP4 ECI positions right now -- the
// same geometry conjunction screening uses, so it's genuinely "what's near
// this satellite", not a decorative list.
function renderNearbyContacts(sat, date) {
  const panel = document.getElementById("contacts-panel");
  const el = document.getElementById("contacts-content");
  if (!panel || !el) return;
  if (!sat || !sat.line1 || !sat.line2) { panel.hidden = true; return; }
  const targetRec = satrecFor(sat);
  const target = targetRec && currentState(targetRec, date);
  if (!target) { panel.hidden = true; return; }

  const items = [];
  for (const e of fleetList()) {
    if (e.norad_id === sat.norad_id || !e.line1 || !e.line2) continue;
    const rec = satrecFor(e);
    if (!rec) continue;
    const st = currentState(rec, date);
    if (!st) continue;
    const dx = st.eci.x - target.eci.x, dy = st.eci.y - target.eci.y, dz = st.eci.z - target.eci.z;
    items.push({ e, d: Math.sqrt(dx * dx + dy * dy + dz * dz) });
  }
  items.sort((a, b) => a.d - b.d);
  const top = items.slice(0, 8);
  panel.hidden = false;
  if (top.length === 0) {
    el.innerHTML = '<span class="panel-note">No other fleet objects to compare against yet.</span>';
    return;
  }
  const curated = curatedIdSet();
  const fmt = (d) => d < 1000 ? `${d.toFixed(0)} km` : `${(d / 1000).toFixed(1)}×10³ km`;
  el.innerHTML =
    `<p class="panel-note">Closest objects in the ${items.length + 1}-object fleet to this satellite right now — straight-line distance between their live SGP4 positions.</p>` +
    top.map(({ e, d }) => {
      const click = curated.has(e.norad_id);
      return `<div class="status-row contact-row${click ? " contact-click" : ""}" data-norad="${e.norad_id}">` +
        `<strong>${e.name}</strong> <span class="label">(${e.norad_id})</span>` +
        `<br><span class="label">${fmt(d)} away${click ? " · click to track" : ""}</span></div>`;
    }).join("");
  el.querySelectorAll(".contact-click").forEach((row) => {
    row.addEventListener("click", () => {
      const id = Number(row.dataset.norad);
      document.getElementById("satellite-select").value = String(id);
      selectSatellite(id);
    });
  });
}

function renderStatus(sat) {
  const el = document.getElementById("status-content");
  const rows = [];

  // Deep space probes (Voyager/Pioneer) aren't Earth-orbiting -- no NORAD
  // TLE, no maneuver detection, no SatNOGS observations apply to them. Real
  // live distance/speed from JPL Horizons instead (see deep_space.py).
  if (sat.deep_space_status) {
    const d = sat.deep_space_status;
    rows.push(`<div class="status-row"><span class="label">Distance from Earth</span><br>` +
      `${d.distance_from_earth_au.toFixed(2)} AU (${(d.distance_from_earth_km / 1e9).toFixed(2)} billion km)</div>`);
    rows.push(`<div class="status-row"><span class="label">Current speed relative to Earth</span><br>${d.speed_km_s.toFixed(2)} km/s</div>`);
    rows.push(`<div class="status-row"><span class="label">Launched</span><br>${d.launched}</div>`);
    rows.push(`<div class="status-row"><span class="label">Computed as of</span><br>${d.epoch} (NASA/JPL Horizons)</div>`);
    el.innerHTML = rows.join("");
    return;
  }

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

  // Full per-satellite maneuver timeline (new in the God's-eye upgrade;
  // empty until the backend regenerates data.json with maneuver_history).
  const timelineHtml = renderManeuverTimeline(sat);
  if (timelineHtml) rows.push(timelineHtml);

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
  if (sat.deep_space_status) {
    updateNote += " The distance/speed above is recomputed by NASA/JPL's Horizons system on every check, from this object's own tracked (or, for a probe NASA has lost contact with, ballistically projected) trajectory.";
  } else if (sat.tle_age_days !== null && sat.tle_age_days !== undefined) {
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

  if (sat.imagery.kind === "commercial") {
    // This satellite genuinely takes Earth imagery, but it's sold
    // commercially -- so we say exactly why there's nothing to show,
    // instead of a bare "no imagery" that looks like a gap.
    el.innerHTML = `<div class="no-imagery">${sat.imagery.reason}</div>`;
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
  if (achievementTimer) clearInterval(achievementTimer);

  const panel = document.getElementById("achievement-panel");
  const el = document.getElementById("achievement-content");
  const items = sat.achievements;

  // Only shown for satellites with at least one real, individually-verified
  // milestone (see achievements.json) -- the panel just stays hidden rather
  // than inventing something for satellites without one.
  if (!items || items.length === 0) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;

  const show = (index) => {
    const item = items[index];
    el.innerHTML = `
      <p class="achievement-headline">${item.headline}</p>
      <p class="achievement-detail">${item.detail}</p>
      ${items.length > 1 ? `<p class="achievement-progress">${index + 1} / ${items.length}</p>` : ""}
    `;
  };

  let current = 0;
  show(current);

  // Cycles through every real achievement this satellite has, like a
  // hint/tip rotation -- only worth doing (and only starts a timer at all)
  // when there's more than one to show.
  if (items.length > 1) {
    achievementTimer = setInterval(() => {
      current = (current + 1) % items.length;
      show(current);
    }, 30000);
  }
}


function renderFireDetection(sat) {
  const panel = document.getElementById("fire-panel");
  const el = document.getElementById("fire-content");

  // Shown ONLY for the four satellites whose own instrument genuinely does
  // active-fire / thermal-hotspot detection -- MODIS on Terra/Aqua, VIIRS
  // on Suomi NPP/NOAA-20 (see site_data.py's _FIRE_SOURCE_BY_NORAD_ID).
  // The fire count is this satellite's OWN instrument's product from NASA
  // FIRMS (genuinely global, not US-only). Because these same thermal
  // sensors are what spot volcanic eruptions from orbit, the USGS volcano
  // alerts ride along here -- and ONLY here -- as honest, clearly-labelled
  // context, not as a claim that this satellite "watches volcanoes".
  if (!sat.fire_detection) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  const fd = sat.fire_detection;
  const parts = [];

  if (fd.count !== null && fd.count !== undefined) {
    parts.push(
      `<div class="status-row"><span class="label">Active fires detected worldwide in the last 24h, by this satellite's ${fd.instrument} instrument (NASA FIRMS)</span>` +
      `<br><strong>${fd.count.toLocaleString()}</strong> fire detections <span class="label">(${fd.source_note})</span></div>`
    );
  } else {
    parts.push(
      `<div class="status-row"><span class="label">Active fire detection (${fd.instrument})</span><br>` +
      'Live count not set up on this deployment yet -- needs a free NASA FIRMS MAP_KEY (see README).</div>'
    );
  }

  // Volcano context -- only shown if there ARE elevated US volcanoes, and
  // explicitly framed as "this same thermal sensor also detects these".
  if (sat.volcano_alerts && sat.volcano_alerts.length > 0) {
    const colorToBadge = { RED: "badge-danger", ORANGE: "badge-warn", YELLOW: "badge-warn", GREEN: "badge-ok" };
    const rows = sat.volcano_alerts.map((v) => `
      <div class="status-row">
        <span class="badge ${colorToBadge[v.color_code] || "badge-warn"}">${v.alert_level}</span>
        <strong>${v.volcano_name}</strong> (${v.observatory})
        <br><span class="label">As of ${v.sent_utc} UTC -- <a href="${v.notice_url}">USGS notice</a></span>
      </div>
    `);
    parts.push(
      '<p class="panel-note" style="margin-top:1rem">Thermal sensors like this also spot volcanic hotspots. ' +
      'For authoritative alert levels, USGS currently lists these US volcanoes as elevated (US-only feed):</p>' +
      rows.join("")
    );
  }

  el.innerHTML = `
    <p class="panel-note">This is real data from this satellite's own ${fd.instrument} instrument, via NASA FIRMS --
    the actual global count of fires it detected in the last 24 hours.</p>
    ${parts.join("")}
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
        <p class="panel-note">Ground weather forecast (Open-Meteo) at this satellite's current position
        (${pos.lat.toFixed(1)}, ${pos.lng.toFixed(1)}) -- a weather-model forecast, not something the satellite
        itself measured.</p>
        ${rows.join("")}
      `;
    })
    .catch(() => {
      el.innerHTML = '<div class="no-imagery">Could not load Open-Meteo forecast right now.</div>';
    });
}

// Fetched client-side, live, at the satellite's current position -- same
// reasoning as the precipitation forecast above (these satellites move too
// fast for an hourly server-side snapshot to still be at the right place).
// "marine" (Sentinel-3A, RADARSAT-2) uses Open-Meteo's real Marine Weather
// API (sea surface temperature/wave height); "wind" (Metop-B) uses
// Open-Meteo's regular forecast wind fields, matching ASCAT's real
// ocean-wind measurement. Real ocean-model/weather-model data either way,
// not something the satellite itself measured at that exact instant.
function renderOceanConditions(sat) {
  const panel = document.getElementById("ocean-panel");
  const el = document.getElementById("ocean-content");

  if (!sat.ocean_context) {
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
  el.innerHTML = "Loading ocean conditions from Open-Meteo...";

  const lat = pos.lat.toFixed(2);
  const lng = pos.lng.toFixed(2);
  const url = sat.ocean_context === "marine"
    ? `https://marine-api.open-meteo.com/v1/marine?latitude=${lat}&longitude=${lng}&hourly=wave_height,sea_surface_temperature&forecast_days=1&timezone=UTC`
    : `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&hourly=wind_speed_10m,wind_direction_10m&forecast_days=1&timezone=UTC`;

  fetch(url)
    .then((r) => r.json())
    .then((data) => {
      const times = data.hourly.time;
      const nowHour = new Date().getUTCHours();
      const idx = Math.max(times.findIndex((t) => new Date(t).getUTCHours() === nowHour), 0);
      const hour = new Date(times[idx]).toISOString().slice(11, 16);

      let rows;
      let note;
      if (sat.ocean_context === "marine") {
        const wave = data.hourly.wave_height[idx];
        const sst = data.hourly.sea_surface_temperature[idx];
        rows = `<div class="status-row"><span class="label">${hour} UTC</span><br>` +
          `${wave === null ? "n/a (land/no ocean-wave model here)" : wave.toFixed(1) + " m wave height"}, ` +
          `${sst === null ? "n/a" : sst.toFixed(1) + " °C sea surface temp"}</div>`;
        note = "Real ocean-model data (Open-Meteo Marine) at this satellite's current position -- " +
          "context for what this kind of satellite observes, not the satellite's own measurement at this instant.";
      } else {
        const speed = data.hourly.wind_speed_10m[idx];
        const dir = data.hourly.wind_direction_10m[idx];
        rows = `<div class="status-row"><span class="label">${hour} UTC</span><br>` +
          `${speed.toFixed(1)} km/h wind, ${dir.toFixed(0)}° direction</div>`;
        note = "Real weather-model wind data (Open-Meteo) at this satellite's current position -- " +
          "matches what its real ASCAT instrument measures (ocean wind speed/direction), though not the satellite's own reading at this instant.";
      }

      el.innerHTML = `<p class="panel-note">${note}</p>${rows}`;
    })
    .catch(() => {
      el.innerHTML = '<div class="no-imagery">Could not load Open-Meteo ocean data right now.</div>';
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
      // EPIC returns every real photo from the latest available day (often
      // 10-20+) -- take more than before so the Earth-photo half of the
      // pool has real variety too, not just the first few.
      images.slice(0, 8).map((img) => {
        const [year, month, day] = img.date.split(" ")[0].split("-");
        return {
          url: `https://epic.gsfc.nasa.gov/archive/natural/${year}/${month}/${day}/png/${img.image}.png`,
          caption: `NASA EPIC (DSCOVR), ${img.date} -- real full-Earth photo from 1 million miles away`,
        };
      })
    )
    .catch(() => []); // EPIC unreachable/rate-limited -- just fewer real photos in the pool, not a crash
}

// A real, varied pool of cosmos search terms -- not just two fixed queries.
// images-api.nasa.gov's search is a static archive search: the same query
// string always returns the same deterministic top results, which is why a
// fixed "hubble nebula" + "james webb space telescope" pair looked like the
// same 6-7 photos every single visit. Picking a random subset of queries,
// AND a random results page for each (real, documented pagination -- see
// https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf), means two
// page loads genuinely see different real photos instead of the same
// deterministic search results every time.
const DEEP_SPACE_QUERIES = [
  "hubble nebula", "james webb space telescope", "spiral galaxy hubble",
  "supernova remnant", "star cluster hubble", "planetary nebula",
  "black hole simulation nasa", "hubble deep field", "star formation nebula",
  "saturn rings cassini", "jupiter juno", "solar eclipse nasa",
  "aurora from space station", "milky way nasa", "exoplanet illustration nasa",
  "galaxy cluster hubble", "orion nebula", "andromeda galaxy",
];

function fetchDeepSpacePhotos() {
  // 6 random queries per load (out of 18 real ones), each on a random page
  // of that query's real results.
  const queries = [...DEEP_SPACE_QUERIES].sort(() => Math.random() - 0.5).slice(0, 6);
  return Promise.all(
    queries.map((q) => {
      const page = 1 + Math.floor(Math.random() * 3);
      return fetch(`https://images-api.nasa.gov/search?q=${encodeURIComponent(q)}&media_type=image&page=${page}`)
        .then((r) => r.json())
        .then((result) => {
          const items = (result.collection && result.collection.items) || [];
          return items
            .slice(0, 4)
            .map((item) => ({
              url: item.links && item.links[0] && item.links[0].href,
              caption: `${(item.data && item.data[0] && item.data[0].title) || "NASA image"} (images.nasa.gov)`,
            }))
            .filter((entry) => entry.url);
        })
        .catch(() => []);
    })
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
  renderFireDetection(sat);
  renderPrecipitationForecast(sat);
  renderOceanConditions(sat);
  renderPasses(sat);
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
      // Select whatever option the dropdown actually shows as chosen (its
      // first <option> in DOM/category order), not data.satellites[0] --
      // those two orderings differ (satellites[] is sorted by NORAD ID,
      // the dropdown is grouped by category), and picking the JSON array's
      // order here previously left the visible dropdown selection and the
      // rendered status/map for two different satellites.
      const select = document.getElementById("satellite-select");

      // A shared "lens" link (#sat=...&t=...&scale=...) reproduces an exact
      // view: select that satellite and restore its simulated time/speed
      // BEFORE tracking starts, so the globe opens on the shared moment
      // rather than snapping to the present first.
      const lens = readUrlHash();
      let selectedId = null;
      if (lens && siteData.satellites.some((s) => s.norad_id === lens.norad_id)) {
        applyLensState(lens);
        selectedId = lens.norad_id;
      } else if (select.options.length > 0) {
        selectedId = Number(select.options[0].value);
      }

      if (selectedId !== null) {
        select.value = String(selectedId);
        selectSatellite(selectedId);
      }
      renderManeuverFeed();
    })
    .catch((err) => {
      document.getElementById("status-content").innerHTML =
        '<div class="no-imagery">Could not load data.json -- has the scheduled workflow run yet?</div>';
      console.error(err);
    });
}

// --- God's eye view: every tracked satellite on the globe at once ---
// The default per-satellite view tracks ONE object; this mode renders the
// whole fleet: every satellite with a TLE becomes a point, orbit trails for
// all of them, and any object with a recent maneuver pulses red. Clicking
// a point drops back into the per-satellite view for that object.
//
// Performance design (this has to stay smooth with hundreds of objects):
//  - SGP4 propagation for all objects runs on a 3s interval, NOT per
//    animation frame (600 propagations = ~ms of work; 60fps would be
//    wasteful since orbital motion is invisible at that granularity).
//  - Orbit trails are computed ONCE per data load in small setTimeout
//    chunks so the page stays responsive while they build.
//  - Points use per-point color/size accessors; hot (recent-maneuver)
//    objects get the pulsing ring treatment.
const godEye = {
  active: false,
  entries: [], // {sat, satrec, recent, curated, category}
  intervalId: null,
  trailsDone: false,
  filter: "__all__",      // category key, or "__all__"
  trailsMode: "important", // "important" | "all" | "none"
};

// Entries matching the current category filter.
function godEyeFiltered() {
  if (godEye.filter === "__all__") return godEye.entries;
  return godEye.entries.filter((e) => (e.sat.category || "uncategorized") === godEye.filter);
}

const GODEYE_UPDATE_MS = 3000;
const GODEYE_TRAIL_POINTS = 36;
const GODEYE_TRAIL_CHUNK = 40;
const MANEUVER_RECENT_DAYS = 7;

// The God's-eye view draws the WHOLE fleet -- every object we have a TLE for
// (the curated watchlist plus the hundreds of group-fetched satellites). The
// backend ships that as `siteData.fleet` (lean: norad_id/name/category/TLE +
// maneuver recency). Older data.json (before the fleet field) falls back to
// the curated `satellites` array so the view still works during a deploy lag.
function fleetList() {
  if (siteData && Array.isArray(siteData.fleet) && siteData.fleet.length > 0) {
    return siteData.fleet;
  }
  return (siteData && siteData.satellites) || [];
}

// "Recently maneuvered" works for both shapes: a fleet entry carries a single
// `last_maneuver` timestamp; a curated satellite carries a maneuver_history.
function maneuveredRecently(entry) {
  let ts = null;
  if (entry.last_maneuver) {
    ts = entry.last_maneuver;
  } else if (entry.maneuver_history && entry.maneuver_history.length > 0) {
    ts = entry.maneuver_history[entry.maneuver_history.length - 1].timestamp;
  }
  if (!ts) return false;
  return Date.now() - new Date(ts).getTime() < MANEUVER_RECENT_DAYS * 86400000;
}

// NORAD IDs that have a full detail page (the dropdown) -- used to tell, in
// God's-eye view, which fleet points can be clicked through to a detail view.
function curatedIdSet() {
  return new Set(((siteData && siteData.satellites) || []).map((s) => s.norad_id));
}

function enterGodEye() {
  if (godEye.active || !siteData) return;
  godEye.active = true;
  document.getElementById("godeye-toggle").classList.add("active");
  document.getElementById("godeye-toggle").innerHTML = "🌍 Exit God's eye";

  // Stop the per-satellite tracking loop and time machine.
  if (simClock.rafId) cancelAnimationFrame(simClock.rafId);
  simClock.rafId = null;
  setTimeMachineVisible(false);

  godEye.entries = [];
  const curated = curatedIdSet();
  for (const sat of fleetList()) {
    const satrec = satrecFor(sat);
    if (!satrec) continue; // deep-space probes / entries without a TLE
    godEye.entries.push({
      sat,
      satrec,
      recent: maneuveredRecently(sat),
      curated: curated.has(sat.norad_id),
    });
  }
  godEye.trailsDone = false;

  // Tell the visitor how many objects are actually on screen -- this scales
  // from the curated ~50 to the full group-fetched fleet (hundreds).
  document.getElementById("godeye-toggle").innerHTML =
    `🌍 Exit God's eye (${godEye.entries.length})`;

  populateGodEyeFilter();
  document.getElementById("godeye-controls").hidden = false;

  // Full-globe camera.
  globeInstance.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 1000);

  // Per-point styling for fleet mode.
  globeInstance
    .pointColor((d) => d.color)
    .pointRadius((d) => d.size)
    .pointLabel((d) => `<div style="font-size:12px">${d.name}` +
      (d.curated ? ' &bull; <span style="color:#58a6ff">click for detail</span>' : '') +
      (d.recent ? '<br><span style="color:#f85149">recent maneuver</span>' : '') +
      `</div>`)
    .ringColor(() => (t) => `rgba(248, 81, 73, ${1 - t})`)
    .pathColor((d) => (d.hot
      ? ["#f85149", "rgba(248, 81, 73, 0.08)"]
      : ["rgba(88, 166, 255, 0.5)", "rgba(88, 166, 255, 0.06)"]))
    .onPointClick((p) => {
      // Only curated satellites have a detail page / dropdown entry; clicking
      // a group-fleet-only object just keeps the hover label (no dead-end
      // navigation into a satellite the panels have no data for).
      if (p && p.norad_id && p.curated) {
        document.getElementById("satellite-select").value = String(p.norad_id);
        exitGodEye();
        selectSatellite(p.norad_id);
      }
    });

  updateGodEyePoints();
  buildGodEyeTrails();
  godEye.intervalId = setInterval(updateGodEyePoints, GODEYE_UPDATE_MS);
}

function exitGodEye() {
  if (!godEye.active) return;
  godEye.active = false;
  if (godEye.intervalId) clearInterval(godEye.intervalId);
  godEye.intervalId = null;
  const toggle = document.getElementById("godeye-toggle");
  toggle.classList.remove("active");
  toggle.innerHTML = "🌍 God's eye view";
  document.getElementById("godeye-controls").hidden = true;
  globeInstance.onPointClick(null);

  // Restore per-satellite styling.
  globeInstance
    .pointColor(() => "#58a6ff")
    .pointRadius(0.7)
    .pointLabel(() => "")
    .ringColor(() => (t) => `rgba(88, 166, 255, ${1 - t})`)
    .pathColor(() => ["#58a6ff", "rgba(88, 166, 255, 0.15)"]);

  // Resume tracking whatever the dropdown shows.
  const select = document.getElementById("satellite-select");
  if (select.value) selectSatellite(Number(select.value));
}

function updateGodEyePoints() {
  if (!godEye.active) return;
  const now = new Date();
  const pts = [];
  const rings = [];
  const entries = godEyeFiltered();
  for (const e of entries) {
    const pos = currentLatLon(e.satrec, now);
    if (!pos) continue;
    pts.push({
      lat: pos.lat, lng: pos.lng,
      norad_id: e.sat.norad_id,
      name: e.sat.name,
      curated: e.curated,
      recent: e.recent,
      color: e.recent ? "#f85149" : (e.curated ? "#58a6ff" : "#8b949e"),
      size: e.recent ? 0.9 : (e.curated ? 0.5 : 0.35),
    });
    if (e.recent) rings.push({ lat: pos.lat, lng: pos.lng });
  }
  globeInstance.pointsData(pts).ringsData(rings);
  const recentCount = entries.filter((e) => e.recent).length;
  const countEl = document.getElementById("godeye-count");
  if (countEl) {
    countEl.textContent = `${pts.length} shown` +
      (recentCount ? ` · ${recentCount} recently maneuvered` : "");
  }
}

function buildGodEyeTrails() {
  // Which objects get an orbit trail depends on the trails mode:
  //  - "none": no trails (just the fleet of points -- cleanest).
  //  - "important": only curated satellites + anything that recently
  //    maneuvered (keeps the globe readable with hundreds of objects while
  //    still drawing the orbits that matter).
  //  - "all": every filtered object (the full dense "whole sky" mesh).
  godEye.trailsDone = false;
  if (godEye.trailsMode === "none") {
    globeInstance.pathsData([]);
    godEye.trailsDone = true;
    return;
  }
  const source = godEyeFiltered().filter((e) =>
    godEye.trailsMode === "all" ? true : (e.curated || e.recent));

  const paths = [];
  let i = 0;
  const now = new Date();
  function chunk() {
    if (!godEye.active) return; // user exited mid-build
    const end = Math.min(i + GODEYE_TRAIL_CHUNK, source.length);
    for (; i < end; i++) {
      const e = source[i];
      const periodMinutes = (2 * Math.PI) / e.satrec.no;
      const pts = [];
      for (let k = 0; k <= GODEYE_TRAIL_POINTS; k++) {
        const t = new Date(now.getTime() + (k / GODEYE_TRAIL_POINTS) * periodMinutes * 60000);
        const pos = currentLatLon(e.satrec, t);
        if (pos) pts.push([pos.lat, pos.lng]);
      }
      if (pts.length > 1) paths.push({ points: pts, hot: !!e.recent });
    }
    globeInstance.pathsData(paths);
    if (i < source.length) {
      setTimeout(chunk, 0);
    } else {
      godEye.trailsDone = true;
    }
  }
  chunk();
}

// Build the category filter dropdown from the categories actually present in
// the fleet, each with a live count, so a visitor can isolate e.g. just
// Starlink or just GPS out of the whole sky.
function populateGodEyeFilter() {
  const sel = document.getElementById("godeye-filter");
  if (!sel) return;
  const labels = (siteData && siteData.category_labels) || {};
  const counts = new Map();
  for (const e of godEye.entries) {
    const c = e.sat.category || "uncategorized";
    counts.set(c, (counts.get(c) || 0) + 1);
  }
  const cats = [...counts.keys()].sort((a, b) => (labels[a] || a).localeCompare(labels[b] || b));
  sel.innerHTML = `<option value="__all__">All categories (${godEye.entries.length})</option>` +
    cats.map((c) => `<option value="${c}">${labels[c] || c} (${counts.get(c)})</option>`).join("");
  sel.value = godEye.filter;
}

function refreshGodEye() {
  if (!godEye.active) return;
  updateGodEyePoints();
  buildGodEyeTrails();
}

// Fleet-wide maneuver feed: every recorded maneuver event across all
// satellites, newest first. Clicking a row jumps to that satellite.
function renderManeuverFeed() {
  const el = document.getElementById("maneuver-feed-content");
  if (!el) return;
  const feed = [];
  for (const sat of siteData.satellites) {
    for (const e of (sat.maneuver_history || [])) {
      feed.push({ sat, e });
    }
  }
  feed.sort((a, b) => new Date(b.e.timestamp) - new Date(a.e.timestamp));
  if (feed.length === 0) {
    el.innerHTML = '<span class="panel-note">No maneuvers detected yet across the fleet.</span>';
    return;
  }
  const total = feed.length;
  const rows = feed.slice(0, 25).map(({ sat, e }) => {
    const when = new Date(e.timestamp).toLocaleString();
    const sig = e.detection ? ` <span class="badge badge-warn">${e.detection}</span>` : "";
    const detail = e.delta_sma_km !== undefined && e.delta_sma_km !== null
      ? `<br><span class="label">Δa ${e.delta_sma_km >= 0 ? "+" : ""}${e.delta_sma_km.toFixed(2)} km · Δi ${e.delta_incl_deg >= 0 ? "+" : ""}${e.delta_incl_deg.toFixed(4)}°</span>`
      : "";
    return `<div class="status-row feed-item" data-norad="${sat.norad_id}">` +
      `<span class="badge badge-danger">MANEUVER</span> <strong>${sat.name}</strong>${sig}` +
      `<br><span class="label">${when}</span>${detail}</div>`;
  });
  el.innerHTML = rows.join("") +
    (total > 25 ? `<div class="panel-note">Showing 25 most recent of ${total} recorded maneuvers.</div>` : "");
  el.querySelectorAll(".feed-item").forEach((row) => {
    row.addEventListener("click", () => {
      const id = Number(row.dataset.norad);
      document.getElementById("satellite-select").value = String(id);
      if (godEye.active) exitGodEye();
      selectSatellite(id);
    });
  });
}

// Per-satellite maneuver timeline in the status panel, from the new
// maneuver_history field (falls back gracefully when the backend hasn't
// regenerated data.json yet).
function renderManeuverTimeline(sat) {
  const hist = sat.maneuver_history;
  if (!hist || hist.length === 0) return "";
  const rows = hist.slice().reverse().map((e) => {
    const sig = e.detection ? ` <span class="badge badge-warn">${e.detection}</span>` : "";
    const detail = (e.delta_sma_km !== undefined && e.delta_sma_km !== null)
      ? `<br><span class="label">Δa ${e.delta_sma_km >= 0 ? "+" : ""}${e.delta_sma_km.toFixed(2)} km · ` +
        `Δi ${e.delta_incl_deg >= 0 ? "+" : ""}${e.delta_incl_deg.toFixed(4)}° · ` +
        `Δe ${e.delta_ecc >= 0 ? "+" : ""}${e.delta_ecc.toFixed(5)}</span>`
      : "";
    return `<div class="status-row"><span class="badge badge-danger">MANEUVER</span>${sig}` +
      `<br><span class="label">${new Date(e.timestamp).toLocaleString()}</span>${detail}</div>`;
  });
  return `<div class="status-row"><span class="label">Maneuver history (${hist.length} recorded)</span></div>` + rows.join("");
}

function wireGodEyeToggle() {
  document.getElementById("godeye-toggle").addEventListener("click", () => {
    if (godEye.active) exitGodEye();
    else enterGodEye();
  });
  const filterSel = document.getElementById("godeye-filter");
  if (filterSel) filterSel.addEventListener("change", () => {
    godEye.filter = filterSel.value;
    refreshGodEye();
  });
  const trailsSel = document.getElementById("godeye-trails");
  if (trailsSel) trailsSel.addEventListener("change", () => {
    godEye.trailsMode = trailsSel.value;
    buildGodEyeTrails();
  });
}

initGlobe();
wireTimeMachineControls();
wireGodEyeToggle();
wireViewControls();
loadData();
startBackdropRotation();
