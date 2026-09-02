import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from app.services.url_security import (
    build_public_network_route_handler,
    validate_public_http_url,
)

CHALLENGE_SIGNALS = [
    "access denied",
    "just a moment",
    "enable javascript",
    "checking your browser",
    "cf-browser-verification",
]


@dataclass
class ScrapedJob:
    job_description: str
    company_name: str | None
    role_title: str | None
    location: str | None
    salary: str | None
    source: Literal["greenhouse_api", "lever_api", "ashby_api", "jina", "crawl4ai"]
    min_salary: int | None = None
    max_salary: int | None = None


def _is_challenge_page(text: str) -> bool:
    if len(text) < 200:
        return True
    lower = text.lower()
    return any(signal in lower for signal in CHALLENGE_SIGNALS)


def _detect_ats(url: str) -> str:
    if "greenhouse.io" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "ashbyhq.com" in url:
        return "ashby"
    if "applytojob.com" in url:
        # JazzHR's candidate-facing hosted career pages live on applytojob.com,
        # not jazzhr.com. No dedicated API handler exists (no stable public
        # read API), so this still falls through to the generic tiers below -
        # kept as a distinct label rather than "generic" for accurate source
        # attribution and to make a future handler a smaller diff.
        return "jazzhr"
    return "generic"


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _scrape_greenhouse(url: str, client: httpx.AsyncClient) -> ScrapedJob:
    """Extract job ID and company token from Greenhouse URL, hit public API."""
    match = re.search(r"greenhouse\.io/(?:v\d/boards/)?([^/]+)/jobs/(\d+)", url)
    if not match:
        raise ValueError("Could not parse Greenhouse URL")
    company, job_id = match.group(1), match.group(2)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"

    r = await client.get(api_url, timeout=10)
    r.raise_for_status()
    data = r.json()

    content = _strip_html(data.get("content", ""))
    title = data.get("title", "")
    dept = (
        data.get("departments", [{}])[0].get("name", "")
        if data.get("departments")
        else ""
    )
    location = (
        data.get("location", {}).get("name", None)
        if isinstance(data.get("location"), dict)
        else data.get("location")
    )
    jd = f"{title}\n{dept}\n\n{content}".strip()
    return ScrapedJob(
        job_description=jd,
        company_name=company.replace("-", " ").title(),
        role_title=title,
        location=location,
        salary=None,
        source="greenhouse_api",
    )


async def _scrape_lever(url: str, client: httpx.AsyncClient) -> ScrapedJob:
    """Extract posting ID from Lever URL, hit public API."""
    match = re.search(r"lever\.co/([^/]+)/([a-f0-9-]+)", url)
    if not match:
        raise ValueError("Could not parse Lever URL")
    company, posting_id = match.group(1), match.group(2)
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"

    r = await client.get(api_url, timeout=10)
    r.raise_for_status()
    data = r.json()

    lists = data.get("lists", [])
    description = data.get("descriptionPlain", "") or data.get("description", "")
    description = _strip_html(description)
    details = "\n".join(
        f"{lst['text']}:\n" + "\n".join(f"- {item}" for item in lst.get("content", []))
        for lst in lists
    )
    jd = f"{data.get('text', '')}\n\n{description}\n\n{details}".strip()
    return ScrapedJob(
        job_description=jd,
        company_name=company.replace("-", " ").title(),
        role_title=data.get("text", ""),
        location=data.get("location"),
        salary=None,
        source="lever_api",
    )


def _ashby_compensation(
    compensation: dict | None,
) -> tuple[int | None, int | None, str | None]:
    """Pull a USD salary range and a display summary out of Ashby's
    compensation payload, when the posting has one."""
    if not compensation:
        return None, None, None
    salary_text = compensation.get("scrapeableCompensationSalarySummary") or compensation.get(
        "compensationTierSummary"
    )
    for component in compensation.get("summaryComponents", []):
        if component.get("compensationType") == "Salary" and component.get("currencyCode") == "USD":
            return component.get("minValue"), component.get("maxValue"), salary_text
    return None, None, salary_text


async def _scrape_ashby(url: str, client: httpx.AsyncClient) -> ScrapedJob:
    """Extract job info from Ashby's public job-board API.

    Ashby job URLs are ashbyhq.com/{company}/{jobId} - no /jobs/ segment.
    The public API has no per-job endpoint; it returns a company's whole
    board, so the target job is found by ID client-side.
    """
    match = re.search(r"ashbyhq\.com/(?:careers/)?([^/]+)/([a-f0-9-]{36})", url)
    if not match:
        raise ValueError("Could not parse Ashby URL")
    company, job_id = match.group(1), match.group(2)
    if company in ("jobs", "careers"):
        raise ValueError("Could not determine Ashby company name from URL")
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"

    r = await client.get(api_url, timeout=10)
    r.raise_for_status()
    data = r.json()

    job_data = next(
        (job for job in data.get("jobs", []) if job.get("id") == job_id), None
    )
    if job_data is None:
        raise ValueError("Job not found on Ashby board")

    title = job_data.get("title", "")
    content = job_data.get("descriptionPlain") or _strip_html(
        job_data.get("descriptionHtml", "")
    )
    location = job_data.get("location")
    jd = f"{title}\n\n{content}".strip()
    min_salary, max_salary, salary_text = _ashby_compensation(job_data.get("compensation"))

    return ScrapedJob(
        job_description=jd,
        company_name=company.replace("-", " ").title(),
        role_title=title,
        location=location,
        salary=salary_text,
        min_salary=min_salary,
        max_salary=max_salary,
        source="ashby_api",
    )


async def _scrape_jina(url: str, client: httpx.AsyncClient) -> str | None:
    """Try Jina Reader; return markdown or None on challenge/failure."""
    jina_url = f"https://r.jina.ai/{url}"
    try:
        r = await client.get(jina_url, timeout=15)
        text = r.text
        if _is_challenge_page(text):
            return None
        return text
    except Exception:
        return None


async def _scrape_crawl4ai(url: str) -> str | None:
    """Try Crawl4AI while blocking requests to non-public networks."""
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        route_handler = build_public_network_route_handler()

        async def install_network_guard(page, context, **kwargs):
            await context.route("**", route_handler)
            return page

        crawler = AsyncWebCrawler(
            config=BrowserConfig(enable_stealth=True)
        )
        crawler.crawler_strategy.set_hook(
            "on_page_context_created", install_network_guard
        )

        async with crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(magic=True),
            )
        return result.markdown or None
    except Exception:
        return None


async def _try_ats_api(
    handler: Callable[[str, httpx.AsyncClient], Awaitable[ScrapedJob]],
    url: str,
    client: httpx.AsyncClient,
) -> ScrapedJob | None:
    """Run an ATS API handler, retrying once on a transient failure.

    Returns None instead of raising so the caller can fall through to the
    generic scraping tiers rather than failing the whole scrape outright.
    """
    attempts = 2
    for attempt in range(attempts):
        try:
            return await handler(url, client)
        except ValueError:
            # URL doesn't match this ATS's expected shape; retrying won't help.
            return None
        except Exception:
            if attempt == attempts - 1:
                return None
    return None


async def scrape_job_url(
    url: str, client: httpx.AsyncClient, provider: str = "auto"
) -> ScrapedJob:
    """
    Tiered scraper:
    1. Greenhouse/Lever/Ashby JSON API (shared async httpx client)
    2. Jina Reader (shared client)
    3. Crawl4AI (local Playwright stealth — uses its own browser)
    4. Raise ValueError if all fail
    """
    await validate_public_http_url(url)
    ats = _detect_ats(url)

    if ats == "greenhouse":
        result = await _try_ats_api(_scrape_greenhouse, url, client)
        if result is not None:
            return result

    elif ats == "lever":
        result = await _try_ats_api(_scrape_lever, url, client)
        if result is not None:
            return result

    elif ats == "ashby":
        result = await _try_ats_api(_scrape_ashby, url, client)
        if result is not None:
            return result

    # Tier 2: Jina
    jina_result = await _scrape_jina(url, client)
    if jina_result:
        return ScrapedJob(
            job_description=jina_result,
            company_name=None,
            role_title=None,
            location=None,
            salary=None,
            source="jina",
        )

    # Tier 3: Crawl4AI (uses its own Playwright browser, not httpx)
    crawl_result = await _scrape_crawl4ai(url)
    if crawl_result:
        return ScrapedJob(
            job_description=crawl_result,
            company_name=None,
            role_title=None,
            location=None,
            salary=None,
            source="crawl4ai",
        )

    raise ValueError("Could not extract job posting. Please paste the text manually.")
