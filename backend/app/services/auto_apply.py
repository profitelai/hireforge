"""Auto-apply service: LinkedIn search scraping, match scoring, and form auto-fill."""

import json
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

# ── LinkedIn URL normalizer ───────────────────────────────────────────────────

def _normalize_linkedin_url(url: str) -> str:
    """Add https:// if missing; convert /jobs/search-results/ to /jobs/search/."""
    import urllib.parse

    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    if "linkedin.com/jobs/search-results" not in url:
        return url

    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    keep = {}
    if "keywords" in params:
        keep["keywords"] = params["keywords"][0]
    if "location" in params:
        keep["location"] = params["location"][0]
    if "geoId" in params:
        keep["geoId"] = params["geoId"][0].split(",")[0]
    if "f_WT" in params:
        keep["f_WT"] = params["f_WT"][0]

    new_qs = urllib.parse.urlencode(keep)
    converted = f"https://www.linkedin.com/jobs/search/?{new_qs}"
    logger.info("Converted search-results URL → %s", converted)
    return converted


# ── LinkedIn search: extract job URLs only ───────────────────────────────────

async def scrape_linkedin_job_urls(
    url: str, max_jobs: int = 50, storage_state: dict | None = None
) -> list[str]:
    """
    Open a LinkedIn jobs search page with the saved session and extract
    all job-view URLs using multiple selector strategies.

    Returns a deduplicated list of canonical job URLs.
    Does NOT attempt to extract job details (company, title, etc.) from the
    search page — those are retrieved per-job by the existing scraper.
    """
    if storage_state is None:
        session_path = os.environ.get("LINKEDIN_SESSION_PATH", "/linkedin_session.json")
        if not os.path.exists(session_path):
            raise ValueError(
                "No LinkedIn session found. Go to Settings → LinkedIn and paste your li_at cookie."
            )
        with open(session_path) as f:
            storage_state = json.load(f)

    cookies = storage_state if isinstance(storage_state, list) else storage_state.get("cookies", [])
    if not any(c.get("name") == "li_at" for c in cookies):
        raise ValueError(
            "LinkedIn session is not authenticated. Go to Settings → LinkedIn and paste your li_at cookie."
        )

    url = _normalize_linkedin_url(url)

    from playwright.async_api import async_playwright

    job_urls: list[str] = []
    seen: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            await page.wait_for_timeout(4000)

            current = page.url
            if "linkedin.com/login" in current or "linkedin.com/authwall" in current:
                raise ValueError(
                    "LinkedIn session expired. Re-authenticate: "
                    "python3 /Users/danimaster/applykit/linkedin_connect.py"
                )

            stale_scrolls = 0
            scroll_rounds = 0

            while len(job_urls) < max_jobs and scroll_rounds < 25:
                prev_count = len(job_urls)

                # Multiple URL extraction strategies — whichever works on today's DOM
                extracted: list[str] = await page.evaluate("""
                    () => {
                        const urls = new Set();

                        // Strategy 1: traditional /jobs/view/ href links
                        document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
                            const href = a.getAttribute('href');
                            if (href) urls.add(href.split('?')[0]);
                        });

                        // Strategy 2: data-job-id attributes
                        document.querySelectorAll('[data-job-id]').forEach(el => {
                            const id = el.getAttribute('data-job-id');
                            if (id && /^\\d+$/.test(id)) urls.add('/jobs/view/' + id + '/');
                        });

                        // Strategy 3: data-occludable-job-id attributes
                        document.querySelectorAll('[data-occludable-job-id]').forEach(el => {
                            const id = el.getAttribute('data-occludable-job-id');
                            if (id && /^\\d+$/.test(id)) urls.add('/jobs/view/' + id + '/');
                        });

                        // Strategy 4: currentJobId in any href
                        document.querySelectorAll('a[href*="currentJobId"]').forEach(a => {
                            const m = (a.getAttribute('href') || '').match(/currentJobId=(\\d+)/);
                            if (m) urls.add('/jobs/view/' + m[1] + '/');
                        });

                        // Strategy 5: job cards by entity urn
                        document.querySelectorAll('[data-entity-urn*="jobPosting"]').forEach(el => {
                            const urn = el.getAttribute('data-entity-urn') || '';
                            const m = urn.match(/(\\d+)$/);
                            if (m) urls.add('/jobs/view/' + m[1] + '/');
                        });

                        return [...urls];
                    }
                """)

                for href in extracted:
                    if len(job_urls) >= max_jobs:
                        break
                    if href.startswith("/"):
                        job_url = "https://www.linkedin.com" + href
                    elif href.startswith("https://"):
                        job_url = href
                    else:
                        continue
                    if job_url not in seen:
                        seen.add(job_url)
                        job_urls.append(job_url)

                logger.info("Scroll %d: %d unique job URLs", scroll_rounds, len(job_urls))

                if len(job_urls) == prev_count:
                    stale_scrolls += 1
                    if stale_scrolls >= 5:
                        logger.info("No new URLs after 5 stale scrolls — stopping.")
                        break
                else:
                    stale_scrolls = 0

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

                try:
                    more_btn = await page.query_selector(
                        "button[aria-label*='more jobs'], "
                        ".infinite-scroller__show-more-button, "
                        "button.jobs-search-results__pagination-btn, "
                        "button[aria-label*='Load more']"
                    )
                    if more_btn:
                        await more_btn.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass

                scroll_rounds += 1

        finally:
            await browser.close()

    logger.info("scrape_linkedin_job_urls: returning %d URLs", len(job_urls))
    return job_urls[:max_jobs]


# ── Greenhouse / Lever / Ashby form auto-fill ─────────────────────────────────

def _detect_ats(url: str) -> str:
    if "greenhouse.io" in url or "grnh.se" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "ashbyhq.com" in url:
        return "ashby"
    return "unknown"


async def auto_apply_greenhouse(
    apply_url: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    resume_pdf: bytes,
    cover_letter: str | None,
) -> dict:
    """Fill and submit a Greenhouse application form."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(apply_url, wait_until="networkidle", timeout=30_000)

            if await page.query_selector('input[name="first_name"]'):
                await page.fill('input[name="first_name"]', first_name)
                await page.fill('input[name="last_name"]', last_name)
            elif await page.query_selector('input[name="name"]'):
                await page.fill('input[name="name"]', f"{first_name} {last_name}")

            for sel in ['input[name="email"]', 'input[type="email"]']:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(email)
                    break

            if phone:
                for sel in ['input[name="phone"]', 'input[type="tel"]']:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(phone)
                        break

            file_input = await page.query_selector('input[type="file"]')
            if file_input and resume_pdf:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(resume_pdf)
                    tmp = f.name
                try:
                    await file_input.set_input_files(tmp)
                finally:
                    os.unlink(tmp)

            if cover_letter:
                for sel in [
                    'textarea[name="cover_letter"]',
                    'textarea[aria-label*="cover"]',
                    'textarea',
                ]:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(cover_letter[:3000])
                        break

            submit = await page.query_selector(
                'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Apply")'
            )
            if not submit:
                return {"ok": False, "message": "Could not find submit button."}

            await submit.click()
            await page.wait_for_timeout(4000)

            body = await page.inner_text("body")
            if any(w in body.lower() for w in ["thank you", "application received", "submitted", "success"]):
                return {"ok": True, "message": "Application submitted."}
            return {"ok": True, "message": "Form submitted — verify manually."}

        except Exception as e:
            return {"ok": False, "message": str(e)}
        finally:
            await browser.close()


async def auto_apply_lever(
    apply_url: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    resume_pdf: bytes,
    cover_letter: str | None,
) -> dict:
    """Fill and submit a Lever application form."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(apply_url, wait_until="networkidle", timeout=30_000)

            full_name = f"{first_name} {last_name}".strip()
            for sel in ['input[name="name"]', 'input[placeholder*="Name"]']:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(full_name)
                    break

            for sel in ['input[name="email"]', 'input[type="email"]']:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(email)
                    break

            if phone:
                for sel in ['input[name="phone"]', 'input[type="tel"]']:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(phone)
                        break

            file_input = await page.query_selector('input[type="file"]')
            if file_input and resume_pdf:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(resume_pdf)
                    tmp = f.name
                try:
                    await file_input.set_input_files(tmp)
                finally:
                    os.unlink(tmp)

            if cover_letter:
                for sel in ['textarea[name="comments"]', 'textarea[placeholder*="cover"]', 'textarea']:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(cover_letter[:3000])
                        break

            submit = await page.query_selector(
                'button[type="submit"], button:has-text("Submit"), button:has-text("Apply")'
            )
            if not submit:
                return {"ok": False, "message": "Could not find submit button."}

            await submit.click()
            await page.wait_for_timeout(4000)

            body = await page.inner_text("body")
            if any(w in body.lower() for w in ["thank you", "application received", "submitted"]):
                return {"ok": True, "message": "Application submitted."}
            return {"ok": True, "message": "Form submitted — verify manually."}

        except Exception as e:
            return {"ok": False, "message": str(e)}
        finally:
            await browser.close()


async def auto_apply(apply_url: str, **kwargs) -> dict:
    """Route to the correct form filler based on ATS."""
    ats = _detect_ats(apply_url)
    if ats == "greenhouse":
        return await auto_apply_greenhouse(apply_url, **kwargs)
    if ats == "lever":
        return await auto_apply_lever(apply_url, **kwargs)
    return {
        "ok": False,
        "message": (
            f"Auto-apply not yet supported for '{ats}' forms. "
            "Open the URL and apply manually with the pre-generated documents."
        ),
    }
