# IIMjobs Auto-Apply — Claude Code Setup

## First-Time Setup

Before starting, make sure you have:

1. **Claude Code CLI** installed (`npm install -g @anthropic-ai/claude-code`)
2. **Playwright MCP** connected in Claude Code settings
3. **IIMjobs account** — you must be logged in via the Playwright browser session
4. **Your config file** — copy `config.example.json` to `config.json` and fill in your details:
   ```bash
   cp config.example.json config.json
   ```
   Then edit `config.json` with your actual CTC, notice period, and preferred job domains.

> `config.json` is gitignored — your personal details stay local.

---

## Auto-Start: Hourly Job Application Loop

At the start of every session, automatically do the following:

1. Check if `config.json` exists in this repo. If it doesn't, remind the user to create it from `config.example.json` and stop.

2. Read the user's preferences from `config.json`.

3. Schedule a recurring hourly loop using CronCreate (cron: `7 * * * *`, recurring: true) with this task:

   > Check IIMjobs for new Product Manager / Senior Product Manager jobs (or whatever roles are in `config.json`) posted in the last hour.
   > - Navigate to https://www.iimjobs.com/jobfeed using Playwright browser
   > - Filter for jobs posted today/in the last hour that match `job_preferences.relevant_domains` in config.json
   > - Skip jobs already in the applications log (applications.db or job_applications_log.md if present)
   > - For each new relevant job, apply via Playwright browser:
   >   - Navigate to the job URL
   >   - Click: `getByRole('button', { name: 'Apply' }).first()`
   >   - If a screening form appears, fill using values from `config.json` screening_answers
   >   - Click Next to submit
   > - Log all applications with date, role, company, and status
   > - **Never use mcp__iimjobs__apply_to_job** — always apply via Playwright browser

4. Confirm the loop is running and tell the user the next fire time.

---

## Screening Form Answers

All screening form answers are read from `config.json → screening_answers`. For any open-ended questions not covered by the config, answer reasonably based on the user's background and the job description.

---

## Stopping the Loop

To cancel the hourly loop at any time, ask Claude: `"Stop the IIMjobs loop"` and it will call CronDelete with the active job ID.
