# orbital-watch

**Live site: https://venkatallu11.github.io/orbital-watch/** — pick a
satellite, see it move in real time, and see its current status/imagery.
Updates automatically every hour (see "Website" below).

A free, open alternative to the "did this satellite maneuver, and should I
be worried?" question that currently gets answered either by a
$2,500/month/satellite commercial SSA subscription (LeoLabs), an
enterprise-only contract (Slingshot Aerospace), or one person doing it by
hand since 1989 (Jonathan McDowell's newsletter).

It automates that manual workflow: watch a list of NORAD IDs, notice
maneuvers, notice collision risk, notice observation anomalies, and write
it all up in plain English — continuously, on a schedule, instead of you
checking three different websites and running your own math.

## What it does

On each scheduled run (`orbital_watch.cli`):
1. Fetches the latest TLE for each watched object.
2. Propagates the *previous* TLE forward to the new TLE's epoch (SGP4) and
   compares predicted vs. actual state — a large mismatch means the object
   did something SGP4 can't explain from the old elements, i.e. it maneuvered.
3. Normalizes that residual by the time gap between the two TLEs (km/day,
   not raw km) before comparing it against the object's *own* rolling
   history — published research on this exact technique flags raw km as
   incomparable across objects with different TLE update cadences (a
   Starlink updated every ~4h vs. an object updated weekly), which is a
   real, documented cause of false positives this fixes. A Starlink
   satellite that station-keeps constantly still doesn't spam alerts, but
   a normally-quiet object that suddenly moves does.
4. Optionally (`--include-socrates`) pulls CelesTrak's free SOCRATES
   conjunction report and filters it to your watchlist — real collision-risk
   awareness without us reimplementing conjunction analysis.
5. Optionally (`--include-satnogs`) checks each object's recent SatNOGS
   observation success rate — an independent physical signal (not just
   catalog data) that something about the object changed.
6. Combines all three into **one digest** instead of three separate manual
   checks, alerts on anything anomalous (console + optional webhook), and
   persists maneuver events so `biography_cli` can show a timeline later.

Three companion tools round out what a manual analyst currently has to
piece together by hand:

- **`biography_cli`** — punch in a NORAD ID, get launch history + owner +
  plain-language maneuver timeline in one page, instead of piecing it
  together from SATCAT codes, Wikipedia, and newsletter archives.
- **`reentry_cli`** — given a nominal reentry time estimate (from an
  existing source — see "What this deliberately does NOT do" below) and its
  uncertainty window, produces the actual ground-track corridor the object
  could come down in, instead of the single false-precision pin/time news
  coverage usually reports.
- **`history_cli`** — reconstructs a satellite's full timeline (residual
  trend + every maneuver ever detected) from git's own commit history of
  `state.json`. No separate log file to maintain: every scheduled run
  already commits state back to the repo, so the history was already
  sitting there one commit per hour — this just walks it and reads it back
  as a clean timeline instead of raw `git log`/`git show` digging.

## Website (`docs/`)

A free static site, deployed on GitHub Pages, that turns the watchlist into
something you can actually click through instead of reading JSON:
**https://venkatallu11.github.io/orbital-watch/**

- **Pick a satellite** from a dropdown of 56 real, currently-tracked
  objects (52 Earth-orbiting + 4 deep-space probes), grouped by category so
  the list stays browsable instead of one giant flat list:
  - **Earth Observation & Weather** (13) — Terra, Aqua, Suomi NPP, NOAA-19,
    NOAA-20, Landsat 8, GOES-16, GOES-18, Meteosat-11, Metop-B, Sentinel-3A,
    RADARSAT-2, Pleiades 1A
  - **Precipitation & Rain/Snow Watch** (2) — GPM Core Observatory (real
    NASA/JAXA rain-rate satellite) and DMSP F18, a real passive-microwave
    weather satellite that's part of the same GPM constellation
  - **Space Telescopes / Deep-Space & Solar Observers** (9) — Hubble,
    Chandra X-ray Observatory, XMM-Newton, Swift, Fermi (FGRST/GLAST), SDO,
    Hinode, NuSTAR, IXPE
  - **Asteroid & Near-Earth Object Watchers** (1) — NEOSSAT, Canada's actual
    orbiting asteroid/comet-survey telescope. Honestly still just one: no
    other dedicated Earth-orbiting NEO-survey satellite turned up in
    CelesTrak's catalogs, and this isn't padded with a less-honest fit.
  - **Space Stations & Human Spaceflight** (6) — ISS (ZARYA + Poisk + Nauka
    modules), CSS (Tianhe + Wentian + Mengtian modules)
  - **Navigation (GNSS)** (9) — GPS, Galileo, BeiDou, GLONASS satellites
  - **Communications Megaconstellations** (7) — Starlink, OneWeb, Iridium
  - **Amateur Radio & CubeSats** (5) — including AO-7, still operating
    since 1974
  - **Deep Space Probes (Not Earth-Orbiting)** (4) — Voyager 1, Voyager 2,
    Pioneer 10, Pioneer 11 (see below)
  - All 52 Earth-orbiting objects were pulled from CelesTrak's live
    GROUP/NAME catalogs (see `discover.py`/the `discover-candidates`
    workflow below), not hand-guessed NORAD IDs.
  - **Not included: Venus/other-planet orbiters, or anything "watching for
    aliens."** This whole system works by propagating NORAD-cataloged
    Earth-orbit TLEs with SGP4 — that method has no meaning for a
    Venus-orbiting or deep-space spacecraft (no Earth-orbit elements exist
    for them), and there's no real spacecraft whose mission is "look for
    aliens" to honestly include. NEOSSAT (asteroids/comets) and the
    Earth-orbiting space telescopes are the closest real equivalents to
    "watching interesting things far away," which is why those categories
    exist instead.
- **Live 3D globe tracking** — a 3D Earth (via `globe.gl`/three.js, real
  night-lights + starfield textures, not a screenshot) whose camera
  continuously follows the selected satellite's current position, with a
  pulsing marker and animated dashed ground track, updated every second
  client-side via `satellite.js` (the same SGP4 math the Python backend
  uses) from the latest TLE already in `data.json`. No live server needed
  for this part — it's just math running on data that's already there.
- **Status panel** — TLE age/freshness, the latest detected maneuver (if
  any), and SatNOGS observation health, straight from the same
  `state.json` the scheduled workflow maintains.
- **"What This Satellite Actually Does" panel** — real per-satellite
  instrument/mission info from `instruments.json` (sourced from genuine
  public mission fact sheets, not fabricated): what instruments it carries
  and what it actually measures for sensing satellites (e.g. GPM's
  GMI/DPR measure rain rate, Metop-B's ASCAT measures ocean wind speed),
  or an honest plain-English description for satellites that don't sense
  anything (GPS/Galileo/BeiDou/GLONASS broadcast navigation signals;
  Starlink/OneWeb/Iridium relay communications) rather than inventing data
  that doesn't exist. Iridium NEXT's real Aireon ADS-B hosted payload
  (global aircraft tracking) is called out specifically.
- **Collision Risk panel** — real CelesTrak SOCRATES conjunction data,
  filtered to whichever satellite the "other object" in a close approach
  involves, persisted from `state.json` (previously this only ever showed
  up in `digest.md`, never on the site itself). Honestly shows "no close
  approaches in the current run" rather than an empty gap when there's
  nothing to report.
- **"Who's Aboard Right Now" panel** — for ISS/Tiangong modules only: real
  names of the people currently in space, from Open Notify's free public
  API. Fetched server-side during the scheduled run (not client-side --
  Open Notify has no HTTPS certificate, so a browser on this HTTPS site
  would silently block a direct fetch to it as mixed content) and baked
  into `data.json`.
- **History panel** — a "Show full history" button that reconstructs the
  satellite's residual/maneuver timeline from git's own commit history of
  `state.json` (see `history.py`), precomputed into `docs/history.json`
  every scheduled run so the site doesn't need a database.
- **Notable Achievement panel** — every one of the 52 tracked satellites
  (plus all 4 deep-space probes) has at least one real, individually
  fact-checked historical milestone (`achievements.json`): flagship
  missions get a genuine unique fact (Hubble's Deep Field, ISS's continuous
  crewed habitation since Nov 2000, AO-7's 21-year revival); individual
  units of a constellation (a specific Starlink, GPS, Galileo, BeiDou,
  GLONASS, OneWeb, or Iridium satellite) honestly get the real achievement
  of the *program* they belong to, rather than a fabricated unique fact for
  that exact unit. Every fact was checked against NASA/JPL/Wikipedia/agency
  sources before being written down, not recalled from memory alone. When a
  satellite has more than one real achievement, the panel cycles through
  them automatically every 30 seconds (like a hint/tip rotation), with a
  small "1 / 2" counter.
- **Deep Space Probes** — Voyager 1, Voyager 2, Pioneer 10, and Pioneer 11
  are real, individually selectable entries in the satellite dropdown,
  under their own "Deep Space Probes" category, exactly like every other
  tracked object. Picking one shows real live distance/speed from NASA/JPL's
  free Horizons API (computed fresh every scheduled run) in the Status
  panel, and real, currently-accurate instrument status in "What This
  Satellite Actually Does" (e.g. Voyager 1 is down to two operating
  instruments as of mid-2026 — NASA has been shutting the rest off to
  conserve its dwindling power supply). These aren't Earth-orbiting (no
  NORAD ID/TLE), so no marker appears on the globe for them — Horizons still
  reports real, physics-computed positions for Pioneer 10/11 even though
  NASA lost contact with them decades ago. Uses JPL Horizons' own real
  (always-negative) spacecraft ID as a stable pseudo-NORAD-ID, so it can
  never collide with a real satellite's ID.
- **Active Fire & Thermal Detection panel**, shown on the **only** four
  satellites whose own instrument actually does this — Terra & Aqua (MODIS)
  and Suomi NPP & NOAA-20 (VIIRS):
  - Real, **global** active-fire detection counts (last 24h) from NASA
    FIRMS, using the FIRMS source that is literally **that satellite's own
    instrument** — MODIS for Terra/Aqua, VIIRS for Suomi NPP/NOAA-20 — so
    each satellite shows the fires *it* detected, not one generic global
    number. (MODIS_NRT is Terra+Aqua combined, which FIRMS doesn't split by
    satellite; the UI says so.) Genuinely worldwide, not US-only. Requires a
    free `FIRMS_MAP_KEY` (see Setup below); honestly says "not set up yet"
    rather than faking a number when that secret isn't configured.
  - Because these same thermal sensors are what spot volcanic hotspots from
    orbit, real-time USGS elevated-volcano alerts ride along here — **and
    only here** — as clearly-labelled context, not as a claim that these
    satellites "watch volcanoes." (USGS's feed is US-only and is the latest
    known status per volcano, both stated honestly.) No other satellite on
    the site shows fire or volcano data, because no other satellite on the
    watchlist detects either.
- **Ground Weather Forecast panel** — for GPM/DMSP (the precipitation-watch
  satellites): a real short-term rain/snowfall forecast (Open-Meteo, free,
  keyless) at the satellite's current live position. Fetched client-side
  at the moment you pick one of these satellites, not baked into
  `data.json` server-side — the satellite keeps moving (GPM orbits roughly
  every 93 minutes), so a forecast computed once an hour and cached would
  already be for the wrong place by the time someone loads the page.
  Labeled honestly as a weather-model forecast, not something the
  satellite itself measured (that's what the real-time GPM rain-rate
  imagery layer above it is for).
- **Ocean Conditions panel** — shown only where the satellite's own
  instrument genuinely measures the quantity: **Sentinel-3A** (real
  sea-surface temperature + wave height via Open-Meteo's free Marine
  Weather API, matching its SLSTR and SRAL instruments) and **Metop-B**
  (real wind speed/direction via Open-Meteo's forecast API, matching its
  ASCAT ocean-wind instrument). RADARSAT-2 is deliberately **excluded** —
  it's a SAR radar imager (sea-ice/ship detection) and does not measure
  sea-surface temperature or waves, so showing that data would misrepresent
  it. Same client-side, satellite's-current-position approach as the ground
  weather forecast, for the same reason.
- **Imagery** — real pictures, not stock photos, matched honestly to what
  each satellite can actually provide, with a switcher when more than one
  real view exists:
  - Terra and Aqua (MODIS) each offer a **whole set** of real, switchable
    GIBS science layers from their own instrument — true color, active
    fire/thermal anomalies, aerosol optical depth, land-surface temperature,
    cloud-top temperature, water vapor, and snow/ice cover — each one
    matching a capability the "What This Satellite Does" panel lists.
  - Suomi NPP and NOAA-20 (VIIRS) offer true-color and active-fire layers.
  - GOES-16 (ABI) shows real GeoColor imagery (GOES-East). GOES-18/West is
    intentionally left out — at the global bounding box the site requests,
    its disc rendered near-blank, so it's omitted rather than shown empty.
  - Every layer identifier was **live-verified** to return a real image
    (see `verify_imagery.py`/the `verify-gibs-layers` workflow) before being
    hardcoded — layers that returned an error (various SST/ozone IDs) were
    dropped, not shipped broken.
  - Landsat 8: GIBS only has an annual composite (WELD product), labeled
    as such rather than claimed to be "live."
  - GPM Core Observatory gets GIBS' real IMERG rain/snowfall-rate layer,
    labeled "realtime" (refreshed every 30 min) and requested for today's
    date since the underlying product isn't a daily composite.
  - Hubble gets NASA's Astronomy Picture of the Day (APOD) — real deep-space
    imagery, honestly captioned as "may or may not be from Hubble
    specifically" since APOD isn't Hubble-exclusive.
  - **RADARSAT-2 and Pleiades 1A are commercial** (MDA/Airbus). They
    genuinely take imagery, but it's sold — there's no free public API for
    it — so their panel says exactly that instead of a bare "no imagery."
  - Everything else (navigation, comms, space stations, most telescopes)
    honestly shows "No public imagery source available" rather than faking
    a picture — those objects don't produce Earth imagery at all.
- **Rotating background of real satellite-captured photos** — cycles every
  60 seconds through a pool of real photos, none stock/fabricated:
  - **GOES-16/18 GeoColor** (NOAA/NESDIS): a fixed CDN URL that always
    serves the current full-disk image, refreshed ~every 10 minutes in
    reality; cache-busted on each rotation so it re-fetches whatever is
    actually current.
  - **NASA EPIC (DSCOVR)**: real full-Earth photos from 1 million miles
    away, refreshed every 60-100 minutes in reality.
  - **NASA images.nasa.gov**: real released photos across 18 different
    real cosmos search terms (nebulae, galaxies, supernova remnants, star
    clusters, planets, etc.) — each page load picks a random 6 of those 18
    queries, each on a random results page, so two visits genuinely see
    different real photos instead of the same deterministic top search
    results every time.
  - Honesty note: the 60-second rotation changes *which* real photo is
    displayed every minute — it does not mean each individual photo's own
    capture refreshes that fast (most of these sources genuinely don't;
    see the per-source cadences above). If every source is unreachable
    (network issue, ad-blocker, or a source down), the page falls back to
    a plain dark background rather than showing a broken image or retrying
    forever -- a real bug found and fixed during testing (the original
    error-fallback retried indefinitely instead of giving up after one
    pass over the photo pool). Also starts on a random photo on page load
    instead of always the same one -- a real bug found in testing (it
    always began at pool index 0).

`docs/data.json` and `docs/history.json` are regenerated every hour by the
same scheduled workflow (via `orbital-watch-site-data` /
`orbital-watch-site-history`) and deployed straight to Pages — the site
always reflects the latest fetch, with no manual step. See the workflow
file's header comment for the one-time "Settings → Pages → Source: GitHub
Actions" toggle a repo owner has to flip once before deploys can succeed
(already done for this repo). The workflow's checkout step uses full git
history (`fetch-depth: 0`) specifically so the history feature has commits
to walk.

**Curating the watchlist further:** `discover_cli.py` (run via the
manual-only `discover-candidates` workflow, since celestrak.org isn't
reachable from every sandbox) lists real, currently-active satellites per
CelesTrak GROUP (stations, weather, science, gps-ops, starlink, etc.) or by
NAME search (e.g. `--names GPM`, used to confirm GPM Core Observatory's
real NORAD ID 39574 before adding it) so new additions are always verified
real objects, not guesses. Similarly, `verify_imagery_cli.py` (via the
manual-only `verify-gibs-layers` workflow) confirms a candidate NASA GIBS
layer identifier actually returns a real image before it's hardcoded.

## Accuracy: what's a real fix vs. a hard ceiling

Public TLE data has a real, permanent precision ceiling no amount of code
fixes: ~1km accuracy right at epoch, degrading to 10s of km after a week
and up to ~100km after 10 days (published studies, see below) — free data
will never match a $2,500/month radar network, and this project says so
rather than overselling.

But research into this exact technique also flagged a **fixable** false-positive
cause that earlier versions didn't account for: raw km residual isn't
comparable across objects with different TLE update cadences. Three fixes,
each grounded in the research, not guessed:
1. **Per-day normalization** (`propagate.py`'s `position_error_km_per_day`)
   — the rolling baseline now compares km/day, not raw km, so a satellite
   updated every 4 hours and one updated weekly are judged on the same
   footing instead of one producing permanently "louder" numbers than the
   other for identical underlying behavior.
2. **TLE staleness surfaced everywhere** (`tle_age_days`) — every digest
   now shows how old each satellite's TLE is, flagged if over a week old,
   so anyone reading a number can judge its confidence themselves instead
   of every figure being presented with the same false precision.
3. **Space-Track/CelesTrak cross-availability** — already in place via the
   fallback logic; both being independently-run catalogs, agreement
   between them (when both are queried) is corroborating evidence.

**Explicitly not attempted, and why:** a real SatNOGS Doppler-shift
cross-check (comparing actual observed radio frequency to predicted) would
improve confidence further, but requires processing raw IQ/audio data — a
legitimately separate signal-processing project, not a quick accuracy fix.
Flagged as real future work, not faked.

## Status: what's actually confirmed live vs. still unverified

This started out built in a network-sandboxed environment, then got run
for real on GitHub Actions against live infrastructure (4 runs, 2026-07-04,
Venkatallu11/orbital-watch). That surfaced and fixed real bugs no amount of
offline testing would have caught — this section reflects that, not just
"tests pass."

As of run #5 (2026-07-04), **the whole pipeline is confirmed working end
to end with real data**, watching 10 real satellites (ISS, Hubble, Terra,
Aqua, Landsat 8, Suomi NPP, NOAA-19, NOAA-20, 2 Starlinks):

- **TLE fetch**: `Fetched 10 TLE(s) for 10 watched object(s).` One of the
  10 (a Starlink launched 2020, plausibly deorbited since) 404'd from
  CelesTrak; the code correctly skips just that one now (see below) or, at
  the time, fell back to Space-Track for the full batch and got all 10.
- **Space-Track fallback**: confirmed genuinely working with a real
  account's credentials, not just mocked.
- **SOCRATES**: real response, `No conjunctions involving your watchlist
  in the current 7-day SOCRATES run` — a legitimate result, not an error.
- **SatNOGS**: real observation-health data for all 10 satellites, e.g.
  `NORAD 37849 (Suomi NPP): 0/25 recent vetted observations were good --
  DEGRADED`, with numbers that changed between consecutive runs (proof
  it's live, not cached).
- **State persistence**: `state.json`/`digest.md` genuinely created and
  committed back to the repo after each run.

**What got fixed along the way, each caught by a real run, not by reasoning
about it in advance:**
- **SatNOGS field names**: the API field is `status` (not `vetted_status`,
  which isn't real) and the filter param is `norad_cat_id` (not
  `satellite__norad_cat_id`) — found by reading satnogs-network's actual
  source on GitLab before any live run, then confirmed correct by real data.
- **CelesTrak batch fetch**: a single comma-joined `CATNR` query for
  multiple IDs silently returns 0 results. Fixed to fetch one ID per
  request, and further hardened so one bad ID (404, decayed satellite)
  is skipped with a warning instead of discarding every other ID's
  already-fetched TLE — while a connection-level failure (the whole site
  unreachable) still propagates, so the Space-Track fallback engages
  instead of silently returning partial results.
- **SOCRATES endpoint path**: the real path is `SOCRATES/table-socrates.php`.
  An earlier "correction" (made before any live run, based on a mistaken
  search result) changed this to `SOCRATES-Plus/table-socrates.php`; a
  real run got a 404 on that exact path, proving it wrong. Reverted.
- **Packaging**: `pip install -r requirements.txt` only installed
  dependencies, not the `orbital_watch` package itself, so the CLI wasn't
  actually importable outside of pytest's test-only path hack. Fixed by
  installing via `pyproject.toml` instead.

**A real, confirmed infrastructure constraint (not a code bug):**
GitHub Actions runners share IP ranges across every workflow on GitHub
worldwide, and CelesTrak's usage policy firewalls IPs that exceed its
bandwidth limits — other projects report the same timeout, and it happened
here too (run #3). That's exactly why the Space-Track fallback exists and
why it's worth configuring those credentials even though CelesTrak alone
sometimes works fine.

**Update (2026-07-05): watchlist expanded from 10 to 50, then 51, real
satellites**, all pulled from CelesTrak's live GROUP/NAME catalogs via
`discover_cli.py` (not hand-guessed). Confirmed on a live run right after
the 10→50 expansion: **all 50 TLEs fetched successfully (zero 404s)**, and
`docs/data.json`/the live site regenerated and deployed without errors.
GPM Core Observatory (NORAD 39574) was added as the 51st satellite after
confirming its real NORAD ID live via `discover_cli.py --names GPM`. The
10-satellite figures above are the original run's real numbers, left as-is
as an honest historical record rather than silently rewritten.

**Still a documented best-guess, flagged in code:** the exact TCA date
format inside the SOCRATES CSV specifically (not yet seen a real response
body with an actual conjunction row to confirm against) — `_parse_tca`
tries ISO 8601 first, falls back to the human-readable format.

**Tested and passing (141 tests, all offline):**
SGP4 residual math and per-object rolling baseline, all parsers (against
fixtures built from confirmed real schemas), the reentry corridor math
(`skyfield`, fully offline), the biography generator, the unified digest,
the Space-Track rate limiter (confirmed to actually be called, not just
constructed), SATCAT owner-based auto-exclusion, the CelesTrak-to-Space-Track
fallback logic (including the per-satellite-vs-connection-failure
distinction above), git-history-based satellite timeline reconstruction
(against real temporary git repos, not mocked, including the
all-satellites-at-once precompute used for the website), the website
data-shaping layer (`site_data.py`, including honest imagery-source
mapping, categories, per-satellite instrument info, conjunctions, and
crew), the CelesTrak GROUP/NAME discovery tool, the GIBS layer verification
tool, the Open Notify crew fetcher, and full end-to-end CLI runs for all
entry points.

Run the self-test below to sanity-check connectivity from wherever you're
deploying this before turning on the schedule:
```bash
pip install -r requirements.txt
python -m orbital_watch.tle_client --selftest
# Expect: "OK: fetched N TLEs (e.g. ISS should be in there)"
```

## What this deliberately does NOT do

- **Doesn't predict reentry timing.** That needs atmospheric density
  modeling (solar activity, drag, tumbling) and even the best models carry
  ~±20% uncertainty on remaining orbital lifetime. `reentry_cli` takes a
  nominal time + uncertainty window as *input* (e.g. from Aerospace Corp's
  or CelesTrak's public decay predictions) and turns it into an honest
  corridor — a communication fix, not a physics upgrade.
- **Doesn't do full Doppler-curve analysis.** A true SatNOGS cross-check
  (comparing observed frequency shift to what the TLE predicts) needs
  signal processing over raw IQ data — a separate project. What's built
  instead is a simpler, still-useful proxy: tracking each object's
  observation *success rate* over time.
- **Isn't real-time and isn't a collision-avoidance system.** Detection
  latency is bounded by how often Space-Track/CelesTrak update a given
  object's TLE (hours to over a week, per object). This is an
  OSINT/awareness tool.
- **No public size/shape data.** USSPACECOM zeroed out RCS values in the
  public SATCAT in 2014; only object category (payload/debris/rocket body)
  is available for free.
- **Can't match LeoLabs/Slingshot precision** — they have real radar/optical
  sensors; this only has public TLEs and free community data.

## Setup

Either install it as a package (gives you the `orbital-watch`,
`orbital-watch-biography`, `orbital-watch-reentry`, `orbital-watch-history` commands directly):
```bash
pip install -e ".[dev]"
pytest tests/ -v      # 84 tests, all offline, no network needed
orbital-watch --help
```
Or just install dependencies and run modules directly with `python -m`:
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
python -m orbital_watch.cli --help
```
The rest of this README uses the `python -m orbital_watch.X` form; swap in
the installed command name if you went the package route.

To use Space-Track (richer/faster-updated catalog than CelesTrak, needed for
non-public/military objects): sign up yourself at
https://www.space-track.org/auth/createAccount (personal registration,
can't be done on your behalf), then:
```bash
export SPACETRACK_USER=you@example.com
export SPACETRACK_PASS=yourpassword
```
`SpaceTrackClient` enforces their documented rate limits itself (<30
requests/min, <300/hour, `ratelimit.py`) by sleeping as needed -- you don't
need to throttle your own polling interval to stay under them.

## Running it

```bash
cp watchlist.example.json watchlist.json   # edit with the NORAD IDs you care about

python -m orbital_watch.cli \
    --watchlist watchlist.json --state state.json \
    --source celestrak \
    --include-socrates --include-satnogs \
    --object-names names.json \
    --exclude-owners-file excluded_owners.json \
    --digest-out digest.md
```

Run this on a schedule — **a working GitHub Actions workflow is included**
at `.github/workflows/orbital-watch.yml` (hourly cron + manual
`workflow_dispatch`), which commits `state.json`/`digest.md` back to the
repo after each run since Actions runners are ephemeral, then generates and
deploys the website (see "Website" above). It needs a real
`watchlist.json` committed (not gitignored, unlike a personal one under a
different filename) — see the workflow file's header comment for the
one-time setup (copy the example, optionally add Space-Track/webhook repo
secrets, and the one-time "Settings → Pages → Source: GitHub Actions"
toggle for the website). Confirmed running live on this repo's own
schedule (see "Status" above for the real run history).

Auto-exclude noisy constellations by owner instead of hand-listing every
object (e.g. skip all Starlink station-keeping burns):
```json
// excluded_owners.json
["SpaceX"]
```
Omit `--satcat-file` to fetch SATCAT live for this; pass it to run fully
offline against a local CSV export instead. If the live fetch fails for
any reason, the run falls back to the unfiltered watchlist rather than
aborting — confirmed by a test that lets the real (blocked, in this
sandbox) network call fail and checks the fallback actually engages.

Optional webhook alerting (Discord/Slack-compatible incoming webhook):
```bash
export ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Optional real, global wildfire detection counts (NASA FIRMS) on the website's
Active Fire & Thermal Detection panel. Unlike NASA's APOD (which has a public
shared DEMO_KEY), FIRMS has no public key — sign up free at
[firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/)
(2 minutes, no cost), then:
```bash
export FIRMS_MAP_KEY=your-key-here
```
Without this set, that panel still shows real US-only volcano status (USGS,
no key needed) and honestly says the fire-detection count isn't configured,
rather than silently omitting it or faking a number.

### Satellite biography

```bash
python -m orbital_watch.biography_cli \
    --norad-id 25544 --state state.json --out iss_biography.md
# omit --satcat-file to fetch live; pass it to run fully offline against a
# local CSV export instead
```

### Reentry corridor

```bash
python -m orbital_watch.reentry_cli \
    --tle-file object.tle \
    --nominal-time 2026-07-10T14:30:00Z --uncertainty-hours 8 \
    --geojson-out corridor.geojson
# open corridor.geojson at geojson.io or any GeoJSON-aware map viewer
```
This was manually smoke-tested end-to-end (not just via pytest) after
installing the package: real corridor computed, real GeoJSON file written.

### Satellite history

```bash
python -m orbital_watch.history_cli \
    --norad-id 25544 --object-name "ISS (ZARYA)" --repo . --out iss_history.md
```
Run this from inside the repo clone (or pass `--repo /path/to/orbital-watch`).
It reconstructs the object's full residual trend and every maneuver ever
detected by walking git's own commit history of `state.json` -- no separate
log file, no schema change, just reading back what the scheduled workflow
already committed one hour at a time. Manually verified against this
project's own real commit history (see "Status" above).

## Known limitations (physics and policy, not implementation gaps)

- **Noisy objects need their own baseline window to fill up**
  (`min_samples`, default 4) before they get a real verdict instead of
  "still building baseline" — or use `--exclude-owners-file` to skip known
  noisy constellations by owner entirely.
- SatNOGS cross-check only works for objects with known amateur-trackable
  transmitters — no help for classified/silent objects.
- Reentry corridor accuracy is only as good as the nominal-time/uncertainty
  estimate you feed it — garbage in, garbage out, by design (see above).
- The scheduled GitHub Actions workflow only fires on a `schedule` trigger
  once it's on the repo's default branch — see the workflow file's header
  comment.

## Architecture

```
src/orbital_watch/
  tle_client.py      TLE fetch (Space-Track / CelesTrak) + parser
  ratelimit.py       Sliding-window rate limiter (Space-Track's documented limits)
  propagate.py       SGP4 residual computation (per-day normalized) + TLE staleness
  baseline.py        Per-object rolling anomaly baseline
  history.py         Satellite timeline reconstruction from git's own state.json commits
  socrates.py        CelesTrak SOCRATES conjunction ingestion + watchlist filter
  satnogs.py         SatNOGS observation-health proxy signal
  satcat.py          SATCAT metadata fetch + parser + owner-based auto-exclusion
  reentry.py         Ground-track uncertainty corridor (skyfield)
  biography.py       Plain-English per-object report
  digest.py          Unified feed combining maneuvers + conjunctions + SatNOGS
  alert.py           Console + webhook alerting
  crew.py            Open Notify "who's in space now" fetch (server-side -- HTTP-only API, see docstring)
  store.py           JSON state persistence between scheduled runs
  cli.py             Main scheduled entry point
  biography_cli.py   Satellite biography entry point
  reentry_cli.py     Reentry corridor entry point
  history_cli.py     Satellite history entry point
  site_data.py       Shapes state.json + watchlist into docs/data.json (pure function, no I/O)
  site_data_cli.py   Website data-generation entry point
  site_history_cli.py  Website history-generation entry point (docs/history.json)
  discover.py        CelesTrak GROUP/NAME catalog fetch, for finding real satellites to add
  discover_cli.py    Watchlist-curation entry point (prints candidates, doesn't modify anything)
  verify_imagery.py     Confirms a candidate GIBS layer returns a real image
  verify_imagery_cli.py Imagery-layer-verification entry point
docs/                Static website (GitHub Pages): index.html, app.js, style.css, data.json + history.json (generated)
watchlist.json       52 real NORAD IDs the scheduled workflow watches
names.json           norad_id -> friendly display name
categories.json      norad_id -> category key (see "Website" above), used for the site's optgroup dropdown
instruments.json     norad_id -> real instrument/mission info (see "Website" above)
tests/               141 tests, fully offline
pyproject.toml       Packaging + console_scripts (orbital-watch, orbital-watch-biography, orbital-watch-reentry, orbital-watch-history, orbital-watch-site-data, orbital-watch-site-history, orbital-watch-discover, orbital-watch-verify-imagery)
.github/workflows/orbital-watch.yml         Scheduled run + website deploy (see above)
.github/workflows/discover-candidates.yml   Manual-only watchlist-curation helper (see "Website" above)
.github/workflows/verify-gibs-layers.yml    Manual-only imagery-layer-verification helper (see "Website" above)
```

## License

MIT — see [LICENSE](LICENSE). Maintained by [Venkatallu11](https://github.com/Venkatallu11).
