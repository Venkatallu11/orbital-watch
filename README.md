# orbital-watch

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
3. Checks that residual against the object's *own* rolling history, not a
   global threshold — a Starlink satellite that station-keeps constantly
   doesn't spam alerts, but a normally-quiet object that suddenly moves does.
4. Optionally (`--include-socrates`) pulls CelesTrak's free SOCRATES
   conjunction report and filters it to your watchlist — real collision-risk
   awareness without us reimplementing conjunction analysis.
5. Optionally (`--include-satnogs`) checks each object's recent SatNOGS
   observation success rate — an independent physical signal (not just
   catalog data) that something about the object changed.
6. Combines all three into **one digest** instead of three separate manual
   checks, alerts on anything anomalous (console + optional webhook), and
   persists maneuver events so `biography_cli` can show a timeline later.

Two companion tools round out what a manual analyst currently has to piece
together by hand:

- **`biography_cli`** — punch in a NORAD ID, get launch history + owner +
  plain-language maneuver timeline in one page, instead of piecing it
  together from SATCAT codes, Wikipedia, and newsletter archives.
- **`reentry_cli`** — given a nominal reentry time estimate (from an
  existing source — see "What this deliberately does NOT do" below) and its
  uncertainty window, produces the actual ground-track corridor the object
  could come down in, instead of the single false-precision pin/time news
  coverage usually reports.

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

**Still a documented best-guess, flagged in code:** the exact TCA date
format inside the SOCRATES CSV specifically (not yet seen a real response
body with an actual conjunction row to confirm against) — `_parse_tca`
tries ISO 8601 first, falls back to the human-readable format.

**Tested and passing (66 tests, all offline):**
SGP4 residual math and per-object rolling baseline, all parsers (against
fixtures built from confirmed real schemas), the reentry corridor math
(`skyfield`, fully offline), the biography generator, the unified digest,
the Space-Track rate limiter (confirmed to actually be called, not just
constructed), SATCAT owner-based auto-exclusion, the CelesTrak-to-Space-Track
fallback logic (including the per-satellite-vs-connection-failure
distinction above), and full end-to-end CLI runs for all three entry points.

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
`orbital-watch-biography`, `orbital-watch-reentry` commands directly):
```bash
pip install -e ".[dev]"
pytest tests/ -v      # 66 tests, all offline, no network needed
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
repo after each run since Actions runners are ephemeral. It needs a real
`watchlist.json` committed (not gitignored, unlike a personal one under a
different filename) — see the workflow file's header comment for the
one-time setup (copy the example, optionally add Space-Track/webhook repo
secrets). It hasn't been run live yet (see "Status" above for why); the
YAML is validated to parse correctly, but confirm it end-to-end once
merged to the default branch.

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
  propagate.py       SGP4 residual computation
  baseline.py        Per-object rolling anomaly baseline
  socrates.py        CelesTrak SOCRATES conjunction ingestion + watchlist filter
  satnogs.py         SatNOGS observation-health proxy signal
  satcat.py          SATCAT metadata fetch + parser + owner-based auto-exclusion
  reentry.py         Ground-track uncertainty corridor (skyfield)
  biography.py       Plain-English per-object report
  digest.py          Unified feed combining maneuvers + conjunctions + SatNOGS
  alert.py           Console + webhook alerting
  store.py           JSON state persistence between scheduled runs
  cli.py             Main scheduled entry point
  biography_cli.py   Satellite biography entry point
  reentry_cli.py     Reentry corridor entry point
tests/               66 tests, fully offline
pyproject.toml       Packaging + console_scripts (orbital-watch, orbital-watch-biography, orbital-watch-reentry)
.github/workflows/orbital-watch.yml   Scheduled run (see above)
```
