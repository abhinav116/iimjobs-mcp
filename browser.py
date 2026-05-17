import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext


class IIMJobsBrowser:
    BASE_URL = "https://www.iimjobs.com"

    def __init__(self):
        self.email = os.environ["IIMJOBS_EMAIL"]
        self.password = os.environ["IIMJOBS_PASSWORD"]
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self, headless: bool = True):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()

    async def login(self) -> bool:
        page = self._page
        await page.goto(f"{self.BASE_URL}/login")
        await page.wait_for_load_state("networkidle")

        await page.fill('input[name="email"], input[type="email"]', self.email)
        await page.fill('input[name="password"], input[type="password"]', self.password)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Check login success by looking for profile/logout elements
        return await page.locator('a[href*="logout"], .user-name, .profile-name').count() > 0

    async def search_jobs(self, role: str, location: str = "",
                          min_exp: int = 0, max_exp: int = 20,
                          min_salary: int = 0) -> list[dict]:
        page = self._page
        search_url = f"{self.BASE_URL}/jobs/search/?searchTerm={role.replace(' ', '+')}"
        if location:
            search_url += f"&location={location.replace(' ', '+')}"

        await page.goto(search_url)
        await page.wait_for_load_state("networkidle")

        jobs = []
        while True:
            job_cards = await page.locator(".job-container, .job-card, article.job").all()

            for card in job_cards:
                try:
                    title_el = card.locator(".job-title, h2 a, .title a").first
                    company_el = card.locator(".company-name, .company, .employer").first
                    location_el = card.locator(".location, .job-location").first
                    salary_el = card.locator(".salary, .ctc, .package").first
                    exp_el = card.locator(".experience, .exp").first
                    link_el = card.locator("a").first

                    title = await title_el.inner_text() if await title_el.count() else ""
                    company = await company_el.inner_text() if await company_el.count() else ""
                    location_text = await location_el.inner_text() if await location_el.count() else ""
                    salary = await salary_el.inner_text() if await salary_el.count() else ""
                    exp = await exp_el.inner_text() if await exp_el.count() else ""
                    href = await link_el.get_attribute("href") if await link_el.count() else ""

                    if not title or not href:
                        continue

                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                    job_id = href.split("/")[-1].split("-")[0] if href else ""

                    jobs.append({
                        "job_id": job_id,
                        "title": title.strip(),
                        "company": company.strip(),
                        "location": location_text.strip(),
                        "salary": salary.strip(),
                        "experience": exp.strip(),
                        "url": job_url,
                    })
                except Exception:
                    continue

            # Pagination
            next_btn = page.locator('a[rel="next"], .next-page, li.next a').first
            if await next_btn.count() and await next_btn.is_enabled():
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
            else:
                break

        return jobs

    async def get_job_details(self, job_url: str) -> dict:
        page = self._page
        await page.goto(job_url)
        await page.wait_for_load_state("networkidle")

        title = await page.locator("h1.job-title, h1, .job-header h1").first.inner_text()
        company = await page.locator(".company-name, .employer-name").first.inner_text()

        jd_el = page.locator(".job-description, .jd-content, #job-description, .description")
        jd_text = await jd_el.first.inner_text() if await jd_el.count() else ""

        salary_el = page.locator(".salary, .ctc-details, .package")
        salary = await salary_el.first.inner_text() if await salary_el.count() else ""

        exp_el = page.locator(".experience, .exp-details")
        experience = await exp_el.first.inner_text() if await exp_el.count() else ""

        return {
            "title": title.strip(),
            "company": company.strip(),
            "jd_text": jd_text.strip(),
            "salary": salary.strip(),
            "experience": experience.strip(),
            "url": job_url,
        }

    async def upload_resume(self, resume_path: Path) -> bool:
        page = self._page
        await page.goto(f"{self.BASE_URL}/candidate/resume")
        await page.wait_for_load_state("networkidle")

        upload_el = page.locator('input[type="file"]').first
        if await upload_el.count():
            await upload_el.set_input_files(str(resume_path))
            await page.click('button[type="submit"], .upload-btn, .save-resume')
            await page.wait_for_load_state("networkidle")
            return True
        return False

    async def apply_to_job(self, job_url: str, resume_path: Path | None = None) -> bool:
        page = self._page
        await page.goto(job_url)
        await page.wait_for_load_state("networkidle")

        # Upload optimized resume before applying if provided
        if resume_path:
            await self.upload_resume(resume_path)
            await page.goto(job_url)
            await page.wait_for_load_state("networkidle")

        # Click apply button
        apply_btn = page.locator('button:has-text("Apply"), a:has-text("Apply Now"), .apply-btn').first
        if not await apply_btn.count():
            return False

        await apply_btn.click()
        await page.wait_for_load_state("networkidle")

        # Handle confirmation modal if present
        confirm_btn = page.locator('button:has-text("Confirm"), button:has-text("Submit"), .confirm-apply')
        if await confirm_btn.count():
            await confirm_btn.first.click()
            await page.wait_for_load_state("networkidle")

        # Verify success
        success_el = page.locator(':has-text("successfully applied"), :has-text("Application submitted"), .success-message')
        return await success_el.count() > 0
