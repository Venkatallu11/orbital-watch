"""Tests the Open Notify crew fetcher (offline, mocked -- Open Notify
isn't reachable from every sandbox, and being HTTP-only it's fetched
server-side anyway, see crew.py's docstring)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.crew import crew_by_craft, fetch_crew  # noqa: E402


class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class _FakeSession:
    def __init__(self, data):
        self.data = data

    def get(self, url, timeout=None):
        return _FakeResponse(self.data)


def test_fetch_crew_parses_people_list():
    session = _FakeSession({
        "message": "success",
        "number": 3,
        "people": [
            {"name": "Jasmin Moghbeli", "craft": "ISS"},
            {"name": "Andreas Mogensen", "craft": "ISS"},
            {"name": "Jing Haiping", "craft": "Tiangong"},
        ],
    })
    crew = fetch_crew(session=session)
    assert len(crew) == 3
    assert crew[0].name == "Jasmin Moghbeli"
    assert crew[0].craft == "ISS"


def test_crew_by_craft_groups_names():
    from orbital_watch.crew import CrewMember

    crew = [
        CrewMember(name="A", craft="ISS"),
        CrewMember(name="B", craft="ISS"),
        CrewMember(name="C", craft="Tiangong"),
    ]
    grouped = crew_by_craft(crew)
    assert grouped == {"ISS": ["A", "B"], "Tiangong": ["C"]}


def test_no_people_returns_empty_list():
    session = _FakeSession({"message": "success", "number": 0, "people": []})
    assert fetch_crew(session=session) == []
