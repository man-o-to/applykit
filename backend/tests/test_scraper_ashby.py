import asyncio

import httpx
import pytest

from app.services.scraper import _ashby_compensation, _scrape_ashby


def _client_returning(json_body: dict, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _board(jobs: list[dict]) -> dict:
    return {"jobs": jobs, "apiVersion": "1"}


def _job(**overrides) -> dict:
    base = {
        "id": "1757f49e-7e19-4c45-85f7-e4637dff66fb",
        "title": "Software Engineer, Agents",
        "location": "North America",
        "descriptionPlain": "About the role...",
        "descriptionHtml": "<p>About the role...</p>",
    }
    base.update(overrides)
    return base


def test_ashby_compensation_extracts_usd_salary_range():
    compensation = {
        "scrapeableCompensationSalarySummary": "$135K - $300K",
        "summaryComponents": [
            {"compensationType": "EquityPercentage", "currencyCode": None},
            {"compensationType": "Salary", "currencyCode": "USD", "minValue": 135000, "maxValue": 300000},
        ],
    }
    min_salary, max_salary, text = _ashby_compensation(compensation)
    assert (min_salary, max_salary, text) == (135000, 300000, "$135K - $300K")


def test_ashby_compensation_returns_none_when_missing():
    assert _ashby_compensation(None) == (None, None, None)
    assert _ashby_compensation({}) == (None, None, None)


def test_ashby_compensation_ignores_non_usd_salary():
    compensation = {
        "summaryComponents": [
            {"compensationType": "Salary", "currencyCode": "EUR", "minValue": 60000, "maxValue": 80000},
        ],
    }
    assert _ashby_compensation(compensation) == (None, None, None)


def test_scrape_ashby_finds_job_by_id_and_extracts_compensation():
    board = _board([
        _job(),
        _job(id="other-job", title="Unrelated"),
    ])
    board["jobs"][0]["compensation"] = {
        "scrapeableCompensationSalarySummary": "$135K - $300K",
        "summaryComponents": [
            {"compensationType": "Salary", "currencyCode": "USD", "minValue": 135000, "maxValue": 300000},
        ],
    }
    client = _client_returning(board)

    result = asyncio.run(
        _scrape_ashby(
            "https://jobs.ashbyhq.com/livekit/1757f49e-7e19-4c45-85f7-e4637dff66fb",
            client,
        )
    )

    assert result.source == "ashby_api"
    assert result.company_name == "Livekit"
    assert result.role_title == "Software Engineer, Agents"
    assert result.location == "North America"
    assert result.min_salary == 135000
    assert result.max_salary == 300000
    assert result.salary == "$135K - $300K"
    assert "About the role" in result.job_description


def test_scrape_ashby_url_without_jobs_segment_is_accepted():
    """Real Ashby job URLs are ashbyhq.com/{company}/{jobId} - no /jobs/ segment."""
    board = _board([_job()])
    client = _client_returning(board)

    result = asyncio.run(
        _scrape_ashby(
            "https://jobs.ashbyhq.com/livekit/1757f49e-7e19-4c45-85f7-e4637dff66fb",
            client,
        )
    )

    assert result.role_title == "Software Engineer, Agents"


def test_scrape_ashby_raises_when_job_not_on_board():
    board = _board([_job(id="some-other-id")])
    client = _client_returning(board)

    with pytest.raises(ValueError):
        asyncio.run(
            _scrape_ashby(
                "https://jobs.ashbyhq.com/livekit/1757f49e-7e19-4c45-85f7-e4637dff66fb",
                client,
            )
        )


def test_scrape_ashby_raises_on_unparseable_url():
    client = _client_returning(_board([]))
    with pytest.raises(ValueError):
        asyncio.run(_scrape_ashby("https://ashbyhq.com/not-a-valid-shape", client))
