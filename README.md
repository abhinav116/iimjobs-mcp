# IIMJobs MCP

An MCP (Model Context Protocol) server that lets Claude automatically search, evaluate, and apply to jobs on [IIMJobs](https://www.iimjobs.com) — with AI-powered resume tailoring for each application.

There are two ways to use this:
- **Claude Code native** (recommended) — drop `CLAUDE.md` into Claude Code, no API costs, applies via browser every hour automatically
- **MCP tools** — call tools explicitly from any MCP-compatible client

---

## Option 1: Claude Code Native (Recommended)

No extra API costs. Claude applies directly via Playwright browser on a cron, resolving the right job feed URL automatically from your role description.

### Setup

**1. Clone the repo**
```bash
git clone https://github.com/abhinav116/iimjobs-mcp.git
cd iimjobs-mcp
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**3. Copy CLAUDE.md to your Claude Code global config**
```bash
# Mac/Linux
cp CLAUDE.md ~/.claude/CLAUDE.md

# Windows
copy CLAUDE.md %USERPROFILE%\.claude\CLAUDE.md
```

**4. Tell Claude your details once**

Just start a conversation and say:
> *"I'm a Strategy Consultant targeting roles in BFSI/consulting. Current CTC 22 LPA, expected 32 LPA, 1 month notice."*

Claude reads this, resolves the right IIMjobs category page from `iimjobs_category_urls.md`, and schedules an hourly cron automatically. You never touch a config file.

### How it works

1. Every hour, Claude navigates to your role's dedicated IIMjobs category page (e.g. `/k/strategy-consulting-jobs`) instead of the generic feed — pre-filtered, no keyword matching needed
2. Filters for jobs posted in the last hour only
3. Cross-checks against your local applications log to skip duplicates
4. Applies via Playwright, fills screening forms with your CTC/notice period
5. Logs everything locally

### Role → URL resolution

Claude automatically picks the right feed URL from `iimjobs_category_urls.md` based on what you tell it. Examples:

| What you say | URL Claude uses |
|---|---|
| "Product Manager / Senior PM" | `/k/it-product-management-jobs` + `/k/ai-product-management-jobs` |
| "Investment Banker" | `/k/investment-banking-jobs` |
| "HR Business Partner" | `/k/hr-business-partner-jobs` |
| "Strategy Consultant" | `/k/strategy-consulting-jobs` |
| "Supply Chain Manager" | `/k/supply-chain-jobs` |

If no category matches, falls back to `https://www.iimjobs.com/jobfeed`.

All available category URLs are in [`iimjobs_category_urls.md`](./iimjobs_category_urls.md).

---

## Option 2: MCP Tools

### What it does

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

### Setup

**1. Clone and install**
```bash
git clone https://github.com/abhinav116/iimjobs-mcp.git
cd iimjobs-mcp
pip install -r requirements.txt
playwright install chromium
```

**2. Configure credentials**
```bash
cp .env.example .env
```
Edit `.env` and fill in:
- `IIMJOBS_EMAIL` and `IIMJOBS_PASSWORD` — your IIMJobs login
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `RESUME_PATH` — path to your resume PDF or DOCX

**3. Register with Claude Code**
```bash
claude mcp add --global iimjobs -- python /full/path/to/iimjobs-mcp/main.py
```

Restart Claude Code. The tools will now be available in any conversation.

### Usage examples

> *"Search for Senior Product Manager roles in Bangalore above 25 LPA"*

> *"Check how well my resume fits this job: [url]"*

> *"Auto-apply to the top 10 AI PM jobs, skip anything below 70% match"*

> *"Show me all my applications"*

> *"Mark job 12345 as interviewing — got a call from Razorpay"*

### Configuration tips

- **`min_match_score`** (default 65) — raise this to be more selective, lower it to cast a wider net
- **`max_applications`** — cap how many jobs it applies to in one run
- **`optimize_resume`** — set to `False` to apply with your original resume (faster, less API cost)

---

## Requirements

- Python 3.10+
- An IIMJobs account (with your resume already uploaded)
- [Claude Code](https://claude.ai/code) or any MCP-compatible client
- An [Anthropic API key](https://console.anthropic.com) (only needed for Option 2 / resume optimization)

## Notes

- All application data is stored locally — never shared anywhere
- The browser runs headless by default. Change `headless=True` to `headless=False` in `browser.py` if you want to watch it work
- Resume optimization (Option 2) uses Claude Sonnet (~$0.01–0.03 per resume). Match scoring uses Claude Haiku (much cheaper)
- Option 1 (Claude Code native) has zero additional API cost beyond your normal Claude Code usage

## Security

- **Never commit your `.env` file** — it's in `.gitignore` by default
- Your IIMJobs credentials are only used locally via Playwright — never sent anywhere else

## Contributing

PRs welcome. Key areas to improve:
- Better Playwright selectors (IIMJobs updates their HTML occasionally)
- Support for Naukri, LinkedIn Easy Apply
- Cover letter generation per JD
