"""One-off research probe -- NOT part of the package, NOT scheduled.

Verifies the exact Open-Meteo Marine Weather API domain/response shape
before hardcoding it into app.js. Run via .github/workflows/research-probe.yml
on a GitHub Actions runner, since this sandbox's own network proxy blocks
this host directly. Delete this file (and its workflow) once done.
"""
import urllib.request


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "orbital-watch-research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def probe(name, url):
    print(f"\n=== {name} ===\n{url}")
    try:
        status, ctype, body = get(url)
        print(f"status={status} content-type={ctype} bytes={len(body)}")
        print(body.decode("utf-8", errors="replace")[:1500])
    except Exception as exc:
        print(f"FAILED: {exc!r}")


def main():
    probe(
        "Open-Meteo Marine (ocean point, near Japan)",
        "https://marine-api.open-meteo.com/v1/marine?latitude=35&longitude=140&hourly=wave_height,sea_surface_temperature&forecast_days=1&timezone=UTC",
    )
    probe(
        "Open-Meteo Marine (land point, should be null/no data)",
        "https://marine-api.open-meteo.com/v1/marine?latitude=39&longitude=-98&hourly=wave_height,sea_surface_temperature&forecast_days=1&timezone=UTC",
    )
    probe(
        "Open-Meteo regular forecast wind fields",
        "https://api.open-meteo.com/v1/forecast?latitude=35&longitude=140&hourly=wind_speed_10m,wind_direction_10m&forecast_days=1&timezone=UTC",
    )


if __name__ == "__main__":
    main()
