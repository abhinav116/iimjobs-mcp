# IIMjobs Auto-Apply — Claude Code Setup

## First-Time Setup

Before starting, make sure you have:

1. **Claude Code CLI** installed (`npm install -g @anthropic-ai/claude-code`)
2. **Playwright MCP** connected in Claude Code settings
3. **IIMjobs account** — you must be logged in via the Playwright browser session

No config file needed. Just tell Claude your role and details once in conversation — it remembers everything across sessions.

---

## Auto-Start: Hourly Job Application Loop

At the start of every session, automatically schedule the following recurring task using CronCreate (cron: `7 * * * *`, recurring: true, durable: true):

**Prompt:**

Resolve the user's job search preferences from memory or from what the user has shared in conversation. Extract:
- ROLE_DESCRIPTION: their target role/function
- CURRENT_CTC: their current compensation
- EXPECTED_CTC: their expected compensation
- NOTICE_PERIOD: their notice period
- BACKGROUND_CONTEXT: their professional background (for answering open-ended screening questions)
- LOG_FILE: path to their job_applications_log.md in memory

Then resolve BASE_URLS:
- Read the IIMjobs category URL map at `iimjobs_category_urls.md` in this repo
- Match ROLE_DESCRIPTION against the keywords in that file to find the best 1-3 category page URLs (e.g. "Product Manager" → `/k/it-product-management-jobs` + `/k/ai-product-management-jobs`)
- If no match found, fall back to https://www.iimjobs.com/jobfeed

For each resolved BASE_URL, check IIMjobs for new jobs posted in the last hour:

1. Navigate to the URL using Playwright browser
2. Filter for jobs posted "today" or "X hours ago" only — skip anything older
3. Skip course/ad listings (those with "course image" in link text)
4. Cross-check against LOG_FILE — skip already-applied jobs
5. For each new job, apply via Playwright browser:
   - Navigate to the job URL
   - Click Apply: `getByRole('button', { name: 'Apply' }).first()`
   - If a screening form appears, fill: current CTC = CURRENT_CTC, expected CTC = EXPECTED_CTC, notice period = NOTICE_PERIOD, location comfort = "Yes", open-ended questions = reasonable answers based on BACKGROUND_CONTEXT
   - Click Next to submit
6. Log all newly applied jobs to LOG_FILE under today's date
7. **Never use mcp__iimjobs__apply_to_job** — always apply via Playwright browser only

After scheduling, confirm the loop is running and tell the user the next fire time.

---

## Stopping the Loop

To cancel the hourly loop at any time, ask Claude: *"Stop the IIMjobs loop"* and it will call CronDelete with the active job ID.
