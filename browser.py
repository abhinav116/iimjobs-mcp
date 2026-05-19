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

    async def ensure_logged_in(self) -> bool:
        """Verify session is active; re-login if expired. Returns True if logged in."""
        await self._page.goto(f"{self.BASE_URL}/jobfeed")
        await self._page.wait_for_load_state("load")
        if "login" in self._page.url:
            return await self.login()
        return True

    async def login(self) -> bool:
        page = self._page
        await page.goto(f"{self.BASE_URL}/login")
        await page.wait_for_load_state("load")

        await page.fill('input[name="email"], input[type="email"]', self.email)
        await page.fill('input[name="password"], input[type="password"]', self.password)
        await page.click('button:has-text("Login"), button[type="submit"], input[type="submit"]')

        # Wait for JS redirect after login
        try:
            await page.wait_for_url(lambda url: "login" not in url, timeout=8000)
        except Exception:
            await page.wait_for_load_state("load", timeout=8000)

        await page.wait_for_timeout(2000)
        return "login" not in page.url

    async def search_jobs(self, role: str, location: str = "",
                          min_exp: int = 0, max_exp: int = 20,
                          min_salary: int = 0) -> list[dict]:
        page = self._page

        # iimjobs jobfeed is personalized to the user's role — use it as the search base
        await page.goto(f"{self.BASE_URL}/jobfeed")
        await page.wait_for_load_state("load")

        # Wait for job cards to render (JS-driven page)
        try:
            await page.wait_for_selector(".joblist-card-v2", timeout=15000)
        except Exception:
            pass

        jobs = []
        while True:
            job_cards = await page.locator(".joblist-card-v2").all()
            if not job_cards:
                break

            for card in job_cards:
                try:
                    link_el = card.locator("a").first
                    title_el = card.locator('[data-testid="job_title"], .joblist__title-text').first
                    exp_el = card.locator('[data-testid="job_experience"]').first
                    location_el = card.locator('[data-testid="job_location"]').first
                    date_el = card.locator('[data-testid="date_posted"]').first

                    href = await link_el.get_attribute("href") if await link_el.count() else ""
                    title = await title_el.inner_text() if await title_el.count() else ""
                    exp = await exp_el.inner_text() if await exp_el.count() else ""
                    location_text = await location_el.inner_text() if await location_el.count() else ""
                    date = await date_el.inner_text() if await date_el.count() else ""

                    if not title or not href:
                        continue

                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                    job_id = href.rstrip("/").split("/")[-1].split("?")[0]

                    # Filter by location if specified
                    if location and location.lower() not in location_text.lower():
                        continue

                    jobs.append({
                        "job_id": job_id,
                        "title": title.strip(),
                        "company": "",
                        "location": location_text.strip(),
                        "salary": "",
                        "experience": exp.strip(),
                        "posted": date.strip(),
                        "url": job_url,
                    })
                except Exception:
                    continue

            # iimjobs uses infinite scroll — no next button; stop after first page
            break

        return jobs

    async def get_job_details(self, job_url: str) -> dict:
        page = self._page
        await page.goto(job_url)
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(3000)

        title = await page.locator("h1").first.inner_text()

        # Company is the first <span> inside the first <a> in .joblist__subtitle
        company_el = page.locator(".joblist__subtitle a span").first
        company = await company_el.inner_text() if await company_el.count() else ""

        # Experience + location live in .joblist__subtitle text
        subtitle_el = page.locator(".joblist__subtitle").first
        subtitle_text = await subtitle_el.inner_text() if await subtitle_el.count() else ""

        # JD: extract from full page text starting at a known section marker
        full_text = await page.locator("body").inner_text()
        jd_text = ""
        for marker in ["Key Responsibilities", "Job Description", "About the Role",
                       "Responsibilities", "About the job"]:
            idx = full_text.find(marker)
            if idx != -1:
                jd_text = full_text[idx:]
                break

        return {
            "title": title.strip(),
            "company": company.strip(),
            "jd_text": jd_text.strip(),
            "salary": "",
            "experience": subtitle_text.strip(),
            "url": job_url,
        }

    async def upload_resume(self, resume_path: Path) -> bool:
        page = self._page
        await page.goto(f"{self.BASE_URL}/candidate/resume")
        await page.wait_for_load_state("load")

        upload_el = page.locator('input[type="file"]').first
        if await upload_el.count():
            await upload_el.set_input_files(str(resume_path))
            await page.click('button[type="submit"], .upload-btn, .save-resume')
            await page.wait_for_load_state("load")
            return True
        return False

    async def get_applied_jobs(self) -> list[dict]:
        page = self._page

        # Navigate directly to the applied jobs page
        await page.goto(f"{self.BASE_URL}/applied-jobs?ref=menu")
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(3000)

        jobs = []
        # Applied jobs page uses a row-based layout
        rows = await page.locator(".applied-job-row, .job-apply-list li, tr.applied-row, .joblist-card-v2, .application-card").all()

        if not rows:
            # Fallback: try to find any job title links on the page
            rows = await page.locator("a[href*='/j/']").all()
            for row in rows:
                try:
                    href = await row.get_attribute("href") or ""
                    title = await row.inner_text()
                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}" if href else ""
                    if title.strip():
                        jobs.append({
                            "title": title.strip(),
                            "company": "",
                            "applied_date": "",
                            "location": "",
                            "status": "Applied/Sent",
                            "url": job_url,
                        })
                except Exception:
                    continue
        else:
            for row in rows:
                try:
                    link_el = row.locator("a[href*='/j/']").first
                    title_el = row.locator(".job-title, .title, h2, h3, a[href*='/j/']").first
                    date_el = row.locator(".applied-date, .date, td:first-child").first
                    status_el = row.locator(".status, .application-status, td:last-child").first

                    href = await link_el.get_attribute("href") if await link_el.count() else ""
                    title = await title_el.inner_text() if await title_el.count() else ""
                    date = await date_el.inner_text() if await date_el.count() else ""
                    status = await status_el.inner_text() if await status_el.count() else "Applied/Sent"
                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}" if href else ""

                    if title.strip():
                        jobs.append({
                            "title": title.strip(),
                            "company": "",
                            "applied_date": date.strip(),
                            "location": "",
                            "status": status.strip(),
                            "url": job_url,
                        })
                except Exception:
                    continue

        if not jobs:
            content = await page.locator("body").inner_text()
            return [{"raw_page_text": content[:3000], "note": "Could not parse structured data, returning raw text"}]

        return jobs

    async def _fill_screening_form(self, answers: dict) -> None:
        """
        Fill all visible screening form fields using label/placeholder matching.
        Handles text inputs, number inputs, selects, radios, and textareas.
        Loops through multiple pages (Next) until Submit or no more navigation.
        """
        page = self._page

        field_map = [
            (["current ctc", "current salary", "present ctc", "current compensation"], answers.get("current_ctc", "")),
            (["expected ctc", "expected salary", "desired ctc", "expected compensation"], answers.get("expected_ctc", "")),
            (["notice period", "notice"], answers.get("notice_period", "")),
            (["total experience", "years of experience", "work experience"], answers.get("experience_years", "")),
        ]

        for _ in range(5):  # up to 5 form pages
            await page.wait_for_timeout(1000)

            # --- Text / Number inputs ---
            for input_el in await page.locator("input[type='text'], input[type='number'], input:not([type])").all():
                try:
                    input_id = await input_el.get_attribute("id") or ""
                    placeholder = (await input_el.get_attribute("placeholder") or "").lower()
                    label_text = ""
                    if input_id:
                        lbl = page.locator(f"label[for='{input_id}']")
                        if await lbl.count():
                            label_text = (await lbl.inner_text()).lower()
                    combined = label_text + " " + placeholder
                    for keywords, value in field_map:
                        if value and any(kw in combined for kw in keywords):
                            await input_el.clear()
                            await input_el.fill(str(value))
                            break
                except Exception:
                    continue

            # --- Select dropdowns ---
            for select_el in await page.locator("select").all():
                try:
                    select_id = await select_el.get_attribute("id") or ""
                    label_text = ""
                    if select_id:
                        lbl = page.locator(f"label[for='{select_id}']")
                        if await lbl.count():
                            label_text = (await lbl.inner_text()).lower()

                    if "notice" in label_text:
                        notice = answers.get("notice_period", "").lower()
                        for opt in await select_el.locator("option").all():
                            opt_text = (await opt.inner_text()).lower()
                            if notice in opt_text or "2 month" in opt_text or "60 day" in opt_text:
                                await select_el.select_option(value=await opt.get_attribute("value"))
                                break
                    elif "relocat" in label_text:
                        try:
                            await select_el.select_option(label="Yes")
                        except Exception:
                            pass
                except Exception:
                    continue

            # --- Radio buttons (relocation yes/no) ---
            for label_el in await page.locator("label").all():
                try:
                    label_text = (await label_el.inner_text()).lower()
                    if "relocat" in label_text:
                        yes_radio = page.locator("input[type='radio'][value='yes'], input[type='radio'][value='Yes'], input[type='radio'][value='1']").first
                        if await yes_radio.count():
                            await yes_radio.click()
                        break
                except Exception:
                    continue

            # --- Textareas (open-ended questions) ---
            for textarea in await page.locator("textarea").all():
                try:
                    if not await textarea.input_value():
                        background = answers.get("background_context", "product management")
                        await textarea.fill(
                            f"I have strong experience in {background}. "
                            "I am excited about this opportunity and confident I can drive measurable impact in this role."
                        )
                except Exception:
                    continue

            # --- Navigate: Next or Submit ---
            next_btn = page.locator("button:has-text('Next'), button:has-text('Continue'), button:has-text('Proceed')").first
            submit_btn = page.locator("button:has-text('Submit'), button[type='submit']").first

            if await next_btn.count():
                await next_btn.click()
                await page.wait_for_timeout(1500)
            elif await submit_btn.count():
                await submit_btn.click()
                await page.wait_for_load_state("load")
                break
            else:
                break

    async def apply_to_job(
        self,
        job_url: str,
        resume_path: Path | None = None,
        screening_answers: dict | None = None,
    ) -> dict:
        """
        Apply to a job. Returns dict with keys: success (bool), reason (str).
        Handles session expiry, screening forms, and external ATS detection.
        """
        page = self._page
        answers = screening_answers or {}

        # Ensure session is still alive before applying
        if not await self.ensure_logged_in():
            return {"success": False, "reason": "Login failed — session could not be restored"}

        await page.goto(job_url)
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1500)

        # Detect external ATS redirect (Workday, Greenhouse, Lever, etc.)
        if self.BASE_URL not in page.url:
            return {"success": False, "reason": f"External ATS detected: {page.url} — skipped"}

        # Upload optimized resume before applying if provided, then return to job page
        if resume_path:
            await self.upload_resume(resume_path)
            await page.wait_for_timeout(2000)  # wait for upload to persist
            await page.goto(job_url)
            await page.wait_for_load_state("load")

        # Detect if already applied
        already = page.locator(":has-text('Already Applied'), :has-text('Application Sent'), .applied-badge")
        if await already.count():
            return {"success": False, "reason": "Already applied (detected on page)"}

        # Click Apply
        apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Now'), .apply-btn").first
        if not await apply_btn.count():
            return {"success": False, "reason": "Apply button not found — job may be closed"}

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Fill screening form if one appeared
        screening_indicators = ["current ctc", "expected ctc", "notice period", "experience", "questionnaire"]
        page_text = (await page.locator("body").inner_text()).lower()
        if any(kw in page_text for kw in screening_indicators):
            await self._fill_screening_form(answers)
        else:
            # Simple confirm modal
            confirm_btn = page.locator("button:has-text('Confirm'), button:has-text('Submit'), .confirm-apply").first
            if await confirm_btn.count():
                await confirm_btn.click()
                await page.wait_for_load_state("load")

        # Verify success — check for success signals or absence of Apply button
        await page.wait_for_timeout(1500)
        success_signals = [
            ":has-text('successfully applied')",
            ":has-text('Application submitted')",
            ":has-text('Applied Successfully')",
            ":has-text('Thank you for applying')",
            ".success-message",
        ]
        for sig in success_signals:
            if await page.locator(sig).count():
                return {"success": True, "reason": ""}

        # Fallback: if Apply button is gone, treat as success
        if not await page.locator("button:has-text('Apply'), a:has-text('Apply Now')").count():
            return {"success": True, "reason": "Apply button disappeared — assumed success"}

        return {"success": False, "reason": "Could not confirm application submission"}
