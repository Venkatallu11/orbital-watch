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

## Status: what's tested vs. what isn't

This was built in a sandboxed environment. Both direct network access
(`celestrak.org`, `space-track.org`, `network.satnogs.org` all return 403 at
the sandbox's network-policy level) and the harness's own page-fetch tool
were tried — the latter revealed these three sites actively block automated
fetches outright (403 on every path, including static files), which is a
property of those sites, not the sandbox. So actual live *data* couldn't be
pulled. What *did* work: fetching these services' own open-source code and
documentation from GitHub/GitLab (not blocked), which let several format
assumptions get checked against ground truth instead of staying guesses.

**Confirmed correct against real source/docs (not just tested logic):**
- **SatNOGS** (`satnogs.py`) — read the actual `satnogs-network` source on
  GitLab (`serializers.py`, `filters.py`, `pagination.py`). This caught two
  real bugs an earlier draft had: the field is `status` (values
  `good`/`bad`/`failed`/`unknown`/`future`), not `vetted_status`, which
  isn't a real field; and the filter query param is `norad_cat_id`, not
  `satellite__norad_cat_id`. Pagination is a fixed `page_size=25` with no
  client-adjustable limit, confirmed the same way. All fixed and tested.
- **SATCAT** (`satcat.py`) — endpoint (`records.php?CATNR=...&FORMAT=CSV`)
  and all 17 CSV columns confirmed verbatim against CelesTrak's own SATCAT
  Format Documentation. This one was right from the start.
- **CelesTrak GP/TLE data** (`tle_client.py`) — `FORMAT=tle` convention
  confirmed against CelesTrak's GP data format documentation.
- **SOCRATES** (`socrates.py`) — real endpoint is
  `SOCRATES-Plus/table-socrates.php` (an earlier guess following SATCAT's
  naming pattern, `SOCRATES/socrates.php`, was wrong), and real CSV columns
  are `OBJECT_NAME_1`/`_2`, `TCA_RANGE`, `DSE_1`/`_2`,
  `TCA_RELATIVE_SPEED`, `DILUTION` (an earlier guess had `NAME_1`/`_2` and
  `MIN_RNG_KM`, both wrong). Both confirmed against multiple independently
  quoted example URLs and CelesTrak's SOCRATES Format Documentation. `CATNR`
  on that endpoint only accepts 1-2 catalog numbers (it's for "conjunctions
  involving object A/between A and B", not a whole watchlist), which is why
  `fetch_conjunctions` pulls the broad current result set and filters
  client-side with `filter_to_watchlist` -- confirmed to match what
  CelesTrak's own docs recommend for exactly this use case.

**Still a documented best-guess, flagged in code:**
- The exact TCA date format inside the SOCRATES CSV specifically (the HTML
  table shows human-readable text; the CSV doc emphasizes RFC 4180/easy
  parsing, suggesting ISO 8601 instead). `_parse_tca` tries both.

**Tested and passing (61 tests, all offline):**
- SGP4 residual math (`propagate.py`) and per-object rolling baseline
  (`baseline.py`), against real `sgp4` objects.
- TLE, SATCAT, and SOCRATES text/CSV parsers, against fixtures now built
  from confirmed real schemas (see above).
- SatNOGS observation-health scoring logic, against the confirmed real
  schema.
- Reentry ground-track corridor math (`reentry.py`), using `skyfield` fully
  offline (builtin timescale, no ephemeris download) against a real TLE.
- The plain-English biography generator (`biography.py`).
- The unified digest assembly (`digest.py`).
- The Space-Track rate limiter (`ratelimit.py`), against a fake clock --
  and confirmed to actually be *called* before every login/query, not just
  constructed and ignored.
- SATCAT owner-based auto-exclusion (`norad_ids_matching_owners`), so
  entire noisy constellations (e.g. all Starlink) can be filtered out of a
  watchlist by owner instead of hand-listing every noisy object.
- **Full end-to-end CLI runs** for all three entry points
  (`cli.py`, `biography_cli.py`, `reentry_cli.py`), using real TLE text
  round-tripped through `sgp4`'s own exporter and monkeypatched network
  calls where a live endpoint would otherwise be needed -- including one
  test where the SATCAT fetch is genuinely, unmockedly attempted and fails
  against this sandbox's blocked network, proving the fallback path for
  real rather than by simulation.

**Still genuinely untested (the HTTP call itself, not the parsing logic):**
`SpaceTrackClient`/`CelesTrakClient` (`tle_client.py`), `fetch_satcat`
(`satcat.py`), `fetch_conjunctions` (`socrates.py`), `fetch_observations`
(`satnogs.py`) — all of these actually reaching their live endpoint and
getting back exactly the confirmed shape above. Run the self-test below
before depending on any of it in production.

Run this before relying on any of the above in production:
```bash
pip install -r requirements.txt
python -m orbital_watch.tle_client --selftest
# Expect: "OK: fetched N TLEs (e.g. ISS should be in there)"
```
If the SOCRATES/SATCAT/SatNOGS live calls turn out to need format
adjustments, that's a small, isolated fix in each module — the parsing
logic itself (the actual hard part) is already tested.

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
pytest tests/ -v      # 61 tests, all offline, no network needed
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
tests/               61 tests, fully offline
pyproject.toml       Packaging + console_scripts (orbital-watch, orbital-watch-biography, orbital-watch-reentry)
.github/workflows/orbital-watch.yml   Scheduled run (see above)
```
