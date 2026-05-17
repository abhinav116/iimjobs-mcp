# IIMJobs MCP

An MCP (Model Context Protocol) server that lets Claude automatically search, evaluate, and apply to jobs on [IIMJobs](https://www.iimjobs.com) — with AI-powered resume tailoring for each application.

## What it does

| Tool | Description |
|---|---|
| `search_jobs` | Search IIMJobs by role, location, experience, salary |
| `get_job_details` | Fetch the full JD for any listing |
| `check_resume_fit` | Score your resume vs a JD (0–100) before applying |
| `apply_to_job` | Apply to one job with an optimized resume |
| `auto_apply_batch` | Search + score + tailor resume + apply to N jobs at once |
| `get_applications` | View all applications and their status |
| `update_application_status` | Mark jobs as interviewing / offered / rejected |

**How auto-apply works:**
1. Searches IIMJobs for your target role
2. Scores your resume against each JD using Claude
3. Skips jobs below your match threshold (default: 65/100)
4. Rewrites your resume to mirror the JD's keywords (without fabricating anything)
5. Uploads the tailored resume to your IIMJobs profile
6. Clicks apply and logs everything to a local SQLite database

## Requirements

- Python 3.10+
- An IIMJobs account (with your resume already uploaded)
- An [Anthropic API key](https://console.anthropic.com)
- [Claude Code](https://claude.ai/code) or any MCP-compatible client

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/iimjobs-mcp.git
cd iimjobs-mcp
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**3. Configure credentials**
```bash
cp .env.example .env
```
Edit `.env` and fill in:
- `IIMJOBS_EMAIL` and `IIMJOBS_PASSWORD` — your IIMJobs login
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `RESUME_PATH` — path to your resume PDF or DOCX (or drop it as `resume.pdf` in this folder)

**4. Register with Claude Code**
```bash
claude mcp add --global iimjobs -- python /full/path/to/iimjobs-mcp/main.py
```

Restart Claude Code. The tools will now be available in any conversation.

## Usage examples

Once set up, just talk to Claude naturally:

> *"Search for Senior Product Manager roles in Bangalore above 25 LPA"*

> *"Check how well my resume fits this job: [url]"*

> *"Auto-apply to the top 10 AI PM jobs, skip anything below 70% match"*

> *"Show me all my applications"*

> *"Mark job 12345 as interviewing — got a call from Razorpay"*

## Configuration tips

- **`min_match_score`** (default 65) — raise this to be more selective, lower it to cast a wider net
- **`max_applications`** — cap how many jobs it applies to in one run
- **`optimize_resume`** — set to `False` to apply with your original resume (faster, less API cost)

## Notes

- This tool automates actions on your behalf. Review the applications it submits via `get_applications`.
- Resume optimization uses Claude Sonnet (costs ~$0.01–0.03 per resume). Match scoring uses Claude Haiku (much cheaper).
- All application data is stored locally in `applications.db` — never shared anywhere.
- The browser runs headless by default. Change `headless=True` to `headless=False` in `browser.py` if you want to watch it work.

## Security

- **Never commit your `.env` file** — it's in `.gitignore` by default
- Your IIMJobs credentials are only used locally via Playwright — they're never sent anywhere else
- The Anthropic API only receives your resume text and JD text for optimization

## Contributing

PRs welcome. Key areas to improve:
- Better Playwright selectors (IIMJobs updates their HTML occasionally)
- Support for Naukri, LinkedIn Easy Apply
- Cover letter generation per JD
