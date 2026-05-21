import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
from browser import IIMJobsBrowser
from resume_optimizer import ResumeOptimizer
from tracker import ApplicationTracker

load_dotenv(Path(__file__).parent / ".env")

mcp = FastMCP("IIMJobs Auto-Apply")
optimizer = ResumeOptimizer()
tracker = ApplicationTracker()

# Extract companies from resume once at startup for blacklist filtering
_resume_companies: list[str] | None = None

def get_resume_companies() -> list[str]:
    global _resume_companies
    if _resume_companies is None:
        try:
            _resume_companies = [c.lower() for c in optimizer.extract_companies()]
        except Exception:
            _resume_companies = []
    return _resume_companies

def is_blacklisted_company(company_name: str) -> bool:
    """Return True if company_name matches any employer in the user's resume."""
    name = company_name.lower()
    return any(rc in name or name in rc for rc in get_resume_companies())


def run_async(coro):
    """Run async code from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@mcp.tool()
def search_jobs(
    role: str,
    location: str = "",
    min_experience: int = 0,
    max_experience: int = 20,
    min_salary_lpa: int = 0,
    max_results: int = 20
) -> list[dict]:
    """
    Search for jobs on IIMJOBS matching the given criteria.

    Args:
        role: Job title or role to search for (e.g. "Product Manager", "Data Scientist")
        location: Preferred location (e.g. "Bangalore", "Mumbai"). Empty for all locations.
        min_experience: Minimum years of experience required
        max_experience: Maximum years of experience
        min_salary_lpa: Minimum salary in LPA
        max_results: Maximum number of results to return

    Returns:
        List of matching jobs with title, company, location, salary, experience, url
    """
    async def _search():
        b = IIMJobsBrowser()
        await b.start(headless=True)
        try:
            await b.login()
            jobs = await b.search_jobs(role, location, min_experience, max_experience, min_salary_lpa)
            return jobs[:max_results]
        finally:
            await b.close()

    return run_async(_search())


@mcp.tool()
def get_job_details(job_url: str) -> dict:
    """
    Get full job description and details for a specific job listing.

    Args:
        job_url: Full URL of the job listing on IIMJOBS

    Returns:
        Dict with title, company, jd_text, salary, experience, url
    """
    async def _get():
        b = IIMJobsBrowser()
        await b.start(headless=True)
        try:
            await b.login()
            return await b.get_job_details(job_url)
        finally:
            await b.close()

    return run_async(_get())


@mcp.tool()
def get_resume_context(job_url: str = "") -> dict:
    """
    Get the current resume text and the optimization instructions.
    Useful for when the client agent needs to perform optimization itself.

    Args:
        job_url: Optional URL of a job to get specific optimization prompt for.

    Returns:
        Dict with resume_text and optimization_prompt
    """
    try:
        resume_text = optimizer.read_resume()
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}

    prompt = ""
    if job_url:
        async def _get_prompt():
            b = IIMJobsBrowser()
            await b.start(headless=True)
            try:
                await b.login()
                details = await b.get_job_details(job_url)
                return optimizer.get_optimization_prompt(
                    details["jd_text"], details["title"], details["company"]
                )
            finally:
                await b.close()
        prompt = run_async(_get_prompt())
    else:
        # Generic prompt template
        prompt = optimizer.get_optimization_prompt("[JD TEXT]", "[JOB TITLE]", "[COMPANY]")

    return {
        "resume_text": resume_text,
        "optimization_prompt": prompt,
        "internal_optimizer_available": bool(optimizer.client)
    }


@mcp.tool()
def check_resume_fit(job_url: str) -> dict:
    """
    Analyze how well your resume matches a specific job before applying.

    Args:
        job_url: Full URL of the job listing

    Returns:
        Dict with score (0-100), matching_skills, missing_skills, recommendation
    """
    async def _check():
        b = IIMJobsBrowser()
        await b.start(headless=True)
        try:
            await b.login()
            details = await b.get_job_details(job_url)
            result = optimizer.get_match_score(details["jd_text"])

            if not optimizer.client:
                # Add instructions for delegation if internal scoring is fallback
                result["action_required"] = "Internal scoring is using fallback. For better accuracy, please analyze the JD and Resume yourself."
                result["jd_text"] = details["jd_text"]
                try:
                    result["resume_text"] = optimizer.read_resume()
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e)}

            return result

        finally:
            await b.close()

    return run_async(_check())


@mcp.tool()
def apply_to_job(
    job_url: str,
    optimize_resume: bool = True,
    provided_resume_text: str = "",
    min_match_score: int = 60,
    current_ctc: str = "",
    expected_ctc: str = "",
    notice_period: str = "",
    experience_years: str = "",
    background_context: str = "",
) -> dict:
    """
    Apply to a single job on IIMJOBS, optionally optimizing your resume for the JD.

    Args:
        job_url: Full URL of the job listing
        optimize_resume: Whether to tailor the resume to this JD before applying
        provided_resume_text: Optimized resume text provided by the client (skips internal LLM)
        min_match_score: Skip application if match score is below this threshold (0-100)
        current_ctc: Current CTC for screening forms (e.g. "38 LPA")
        expected_ctc: Expected CTC for screening forms (e.g. "45 LPA")
        notice_period: Notice period for screening forms (e.g. "2 months")
        experience_years: Total years of experience for screening forms (e.g. "8")
        background_context: Brief background for open-ended screening questions

    Returns:
        Dict with success status, job details, match_score, resume_version used.
        If internal optimizer is missing and no text is provided, returns delegation instructions.
    """
    async def _apply():
        b = IIMJobsBrowser()
        await b.start(headless=True)
        try:
            await b.login()
            details = await b.get_job_details(job_url)
            job_id = job_url.rstrip("/").split("/")[-1].split("?")[0]

            if tracker.already_applied(job_id):
                return {"success": False, "reason": "Already applied to this job", "job": details}

            if is_blacklisted_company(details.get("company", "")):
                return {"success": False, "reason": f"Skipped — {details['company']} is a past/current employer", "job": details}

            # FALLBACK LOGIC: No internal optimizer and no provided text
            if optimize_resume and not provided_resume_text and not optimizer.client:
                try:
                    resume_text = optimizer.read_resume()
                    opt_prompt = optimizer.get_optimization_prompt(
                        details["jd_text"], details["title"], details["company"]
                    )
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e)}

                return {
                    "success": False,
                    "reason": "Internal optimizer unavailable (No API key).",
                    "action_required": "Please optimize the resume text yourself using the provided prompt and resume context. Then call 'apply_to_job' again with 'provided_resume_text'.",
                    "optimization_prompt": opt_prompt,
                    "resume_text": resume_text,
                    "job_details": details
                }

            # Cleanup provided text (strip markdown if agent included it)
            if provided_resume_text:
                provided_resume_text = provided_resume_text.strip()
                if provided_resume_text.startswith("```"):
                    # Remove ```text ... ``` or just ``` ... ```
                    lines = provided_resume_text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    provided_resume_text = "\n".join(lines).strip()

            resume_path = None
            resume_version = "original"
            match_score = 100

            if provided_resume_text:
                resume_path = optimizer.get_optimized_resume_path(
                    job_id, details["jd_text"], details["title"], details["company"],
                    provided_text=provided_resume_text
                )
                resume_version = f"delegated_{job_id}"
            elif optimize_resume:
                score_data = optimizer.get_match_score(details["jd_text"])
                match_score = score_data.get("score", 0)

                if match_score < min_match_score:
                    return {
                        "success": False,
                        "reason": f"Match score {match_score} below threshold {min_match_score}",
                        "score_details": score_data,
                        "job": details
                    }

                resume_path = optimizer.get_optimized_resume_path(
                    job_id, details["jd_text"], details["title"], details["company"]
                )
                resume_version = f"optimized_{job_id}"

            screening_answers = {
                "current_ctc": current_ctc,
                "expected_ctc": expected_ctc,
                "notice_period": notice_period,
                "experience_years": experience_years,
                "background_context": background_context,
            }

            result = await b.apply_to_job(job_url, resume_path, screening_answers)

            if result["success"]:
                tracker.add(
                    job_id=job_id,
                    title=details["title"],
                    company=details["company"],
                    location=details.get("location", ""),
                    salary=details.get("salary", ""),
                    job_url=job_url,
                    resume_version=resume_version
                )

            return {
                "success": result["success"],
                "reason": result.get("reason", ""),
                "job": details,
                "match_score": match_score,
                "resume_version": resume_version
            }
        finally:
            await b.close()

    return run_async(_apply())


@mcp.tool()
def auto_apply_batch(
    role: str,
    location: str = "",
    min_experience: int = 0,
    max_experience: int = 20,
    min_salary_lpa: int = 0,
    min_match_score: int = 65,
    max_applications: int = 10,
    optimize_resume: bool = True,
    current_ctc: str = "",
    expected_ctc: str = "",
    notice_period: str = "",
    experience_years: str = "",
    background_context: str = "",
) -> dict:
    """
    Search for jobs matching criteria and automatically apply to all of them.
    Skips jobs already applied to. Optimizes resume for each JD.

    Args:
        role: Job title to search for
        location: Preferred location (empty for all)
        min_experience: Minimum years of experience
        max_experience: Maximum years of experience
        min_salary_lpa: Minimum salary in LPA
        min_match_score: Only apply if resume match score >= this (0-100)
        max_applications: Maximum number of applications to submit in this run
        optimize_resume: Whether to tailor resume for each JD

    Returns:
        Summary with applied_count, skipped_count, failed_count, and details per job.
        If internal optimizer is missing, returns list of jobs for client to process individually.
    """
    async def _batch():
        b = IIMJobsBrowser()
        await b.start(headless=True)

        # FALLBACK LOGIC: Batch optimization requested but no internal optimizer
        if optimize_resume and not optimizer.client:
            try:
                await b.login()
                jobs = await b.search_jobs(role, location, min_experience, max_experience, min_salary_lpa)
                filtered_jobs = []
                for job in jobs:
                    job_id = job["url"].rstrip("/").split("/")[-1].split("?")[0]
                    if not tracker.already_applied(job_id) and not is_blacklisted_company(job.get("company", "")):
                        filtered_jobs.append(job)
                    if len(filtered_jobs) >= max_applications:
                        break

                try:
                    resume_text = optimizer.read_resume()
                    opt_instructions = optimizer.get_optimization_prompt("[JD]", "[TITLE]", "[COMPANY]")
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e)}

                return {
                    "success": False,
                    "reason": "Internal optimizer unavailable for batch processing.",
                    "action_required": "Please iterate through these jobs and call 'apply_to_job' for each, providing optimized text from your own intelligence.",
                    "jobs_to_process": filtered_jobs,
                    "resume_text": resume_text,
                    "optimization_instructions": opt_instructions
                }
            finally:
                await b.close()

        # Original batch logic continues only if internal optimizer is available
        results = {
            "applied": [],
            "skipped": [],
            "failed": [],
            "applied_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
        }

        try:
            await b.login()
            jobs = await b.search_jobs(role, location, min_experience, max_experience, min_salary_lpa)

            for job in jobs:
                if results["applied_count"] >= max_applications:
                    break

                job_id = job["url"].rstrip("/").split("/")[-1].split("?")[0]

                if tracker.already_applied(job_id):
                    results["skipped"].append({"job": job, "reason": "Already applied"})
                    results["skipped_count"] += 1
                    continue

                if is_blacklisted_company(job.get("company", "")):
                    results["skipped"].append({"job": job, "reason": "Past/current employer"})
                    results["skipped_count"] += 1
                    continue

                try:
                    details = await b.get_job_details(job["url"])
                    resume_path = None
                    resume_version = "original"
                    match_score = 100

                    if optimize_resume:
                        score_data = optimizer.get_match_score(details["jd_text"])
                        match_score = score_data.get("score", 0)

                        if match_score < min_match_score:
                            results["skipped"].append({
                                "job": job,
                                "reason": f"Low match score: {match_score}"
                            })
                            results["skipped_count"] += 1
                            continue

                        resume_path = optimizer.get_optimized_resume_path(
                            job_id, details["jd_text"], details["title"], details["company"]
                        )
                        resume_version = f"optimized_{job_id}"

                    screening_answers = {
                        "current_ctc": current_ctc,
                        "expected_ctc": expected_ctc,
                        "notice_period": notice_period,
                        "experience_years": experience_years,
                        "background_context": background_context,
                    }

                    result = await b.apply_to_job(job["url"], resume_path, screening_answers)

                    if result["success"]:
                        tracker.add(
                            job_id=job_id,
                            title=job["title"],
                            company=job["company"],
                            location=job.get("location", ""),
                            salary=job.get("salary", ""),
                            job_url=job["url"],
                            resume_version=resume_version
                        )
                        results["applied"].append({
                            "job": job,
                            "match_score": match_score,
                            "resume_version": resume_version
                        })
                        results["applied_count"] += 1
                    else:
                        results["failed"].append({"job": job, "reason": result.get("reason", "Unknown")})
                        results["failed_count"] += 1

                except Exception as e:
                    results["failed"].append({"job": job, "reason": str(e)})
                    results["failed_count"] += 1

        finally:
            await b.close()

        return results

    return run_async(_batch())


@mcp.tool()
def get_applied_jobs_from_iimjobs() -> list[dict]:
    """
    Log into IIMJobs and retrieve all jobs you have applied to directly from the website.
    This includes manually applied jobs, not just ones applied through this MCP.

    Returns:
        List of applied jobs with title, company, applied_date, status, and url
    """
    async def _fetch():
        b = IIMJobsBrowser()
        await b.start(headless=True)
        try:
            return await b.get_applied_jobs()
        finally:
            await b.close()

    return run_async(_fetch())


@mcp.tool()
def get_applications(status_filter: str = "") -> list[dict]:
    """
    View all jobs you have applied to, with status tracking.

    Args:
        status_filter: Filter by status ('applied', 'interviewing', 'rejected', 'offered').
                      Empty string returns all.

    Returns:
        List of applications with job details and current status
    """
    apps = tracker.get_all()
    if status_filter:
        apps = [a for a in apps if a["status"] == status_filter]
    return apps


@mcp.tool()
def update_application_status(job_id: str, status: str, notes: str = "") -> dict:
    """
    Update the status of a job application (e.g. after getting a call).

    Args:
        job_id: Job ID from the application list
        status: New status — one of: 'applied', 'interviewing', 'rejected', 'offered', 'accepted'
        notes: Optional notes (e.g. "HR called, interview on Monday")

    Returns:
        Confirmation of update
    """
    valid_statuses = {"applied", "interviewing", "rejected", "offered", "accepted"}
    if status not in valid_statuses:
        return {"success": False, "error": f"Invalid status. Use one of: {valid_statuses}"}
    tracker.update_status(job_id, status, notes)
    return {"success": True, "job_id": job_id, "status": status}


if __name__ == "__main__":
    mcp.run()
