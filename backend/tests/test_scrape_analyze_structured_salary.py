import asyncio

from app.routes import scrape
from app.schemas import ParseJobDescriptionResponse, ScrapeAnalyzeRequest
from app.services.scraper import ScrapedJob


def test_structured_salary_comes_from_the_llm_parse_not_the_scraper(monkeypatch):
    """ScrapedJob never carries structured salary - min_salary/max_salary must
    always come from parse_job_description, even when the scraper tier itself
    already supplied other authoritative fields like company_name."""

    async def fake_scrape_job_url(url: str, client) -> ScrapedJob:
        return ScrapedJob(
            job_description="Senior Engineer - $140,000 - $170,000 per year.",
            company_name="Acme",
            role_title="Senior Engineer",
            location="Remote",
            salary=None,
            source="greenhouse_api",
        )

    def fake_parse_job_description(*args, **kwargs) -> ParseJobDescriptionResponse:
        return ParseJobDescriptionResponse(
            company_name="Acme",
            role_title="Senior Engineer",
            location="Remote",
            salary="$140,000 - $170,000 per year",
            min_salary=140000,
            max_salary=170000,
        )

    monkeypatch.setattr(scrape, "require_llm_config", lambda db: ("openai", "secret"))
    monkeypatch.setattr(scrape, "scrape_job_url", fake_scrape_job_url)
    monkeypatch.setattr(scrape, "parse_job_description", fake_parse_job_description)

    result = asyncio.run(
        scrape.scrape_analyze(
            ScrapeAnalyzeRequest(url="https://job-boards.greenhouse.io/acme/jobs/1"),
            db=object(),
            client=object(),
        )
    )

    assert result.min_salary == 140000
    assert result.max_salary == 170000


def test_structured_salary_defaults_to_none_when_the_llm_cannot_extract_it(monkeypatch):
    def fake_parse_job_description(*args, **kwargs) -> ParseJobDescriptionResponse:
        return ParseJobDescriptionResponse(
            company_name=None,
            role_title=None,
            location=None,
            salary=None,
        )

    monkeypatch.setattr(scrape, "require_llm_config", lambda db: ("openai", "secret"))
    monkeypatch.setattr(scrape, "parse_job_description", fake_parse_job_description)

    result = asyncio.run(
        scrape.scrape_analyze(
            ScrapeAnalyzeRequest(text="A job description with no salary mentioned."),
            db=object(),
            client=object(),
        )
    )

    assert result.min_salary is None
    assert result.max_salary is None
