import os
import re
from pathlib import Path
import pdfplumber
import anthropic
from fpdf import FPDF


class ResumeOptimizer:
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        try:
            self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        except Exception:
            self.client = None

        resume_env = os.environ.get("RESUME_PATH", "")
        self.resume_path = Path(resume_env) if resume_env else Path(__file__).parent / "resume.pdf"
        self._resume_text: str | None = None

    def read_resume(self) -> str:
        if self._resume_text:
            return self._resume_text
        if not self.resume_path.exists():
            raise FileNotFoundError(f"Resume not found at {self.resume_path}. Please set RESUME_PATH in .env or upload resume.pdf")

        suffix = self.resume_path.suffix.lower()
        if suffix == ".pdf":
            with pdfplumber.open(self.resume_path) as pdf:
                self._resume_text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        elif suffix == ".docx":
            from docx import Document
            doc = Document(self.resume_path)
            self._resume_text = "\n".join(p.text for p in doc.paragraphs)
        else:
            raise ValueError(f"Unsupported resume format: {suffix}")
        return self._resume_text

    def get_optimization_prompt(self, jd_text: str, job_title: str, company: str) -> str:
        resume_text = self.read_resume()
        return f"""You are an expert resume writer and ATS optimization specialist.

I am applying for the role of **{job_title}** at **{company}**.

Here is the Job Description:
<jd>
{jd_text}
</jd>

Here is my current resume:
<resume>
{resume_text}
</resume>

Your task:
1. Rewrite my resume to maximize alignment with this specific JD
2. Mirror keywords and phrases from the JD naturally throughout the summary and bullet points
3. Reorder and front-load bullet points that most directly match the role's requirements
4. Quantify achievements wherever possible — keep all existing numbers, add context where missing
5. Do NOT fabricate experience, skills, companies, or metrics — only reframe what exists
6. Keep the same sections: header, summary, EXPERIENCE, SKILLS
7. In the SKILLS section, add any relevant skills mentioned in JD that the candidate genuinely has
8. Output the resume in this exact plain-text format (no markdown, no asterisks):

ABHINAV MARDA
Phone: 9959791067 | Email: abhinav.marda@gmail.com | LinkedIn: linkedin.com/in/abhinav-marda-84015287
Education: MBA from IIM Calcutta (2019-2021) | B.Tech CSE, IIT Indore (2012-2016)

[One paragraph summary tailored to this role]

EXPERIENCE

[Company Name]
[Role Title] | [Date range]
- bullet
- bullet

[Continue for all companies in reverse chronological order]

SKILLS
Product Skills: ...
Project Management Tools: ...
Tech Stack: ...

Output ONLY the resume text, no commentary."""

    def optimize(self, jd_text: str, job_title: str, company: str) -> str:
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured. Cannot optimize internally.")

        prompt = self.get_optimization_prompt(jd_text, job_title, company)
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    def save_as_pdf(self, text: str, output_path: Path) -> Path:
        pdf = FPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(left=15, top=15, right=15)
        pdf.add_page()

        SECTION_HEADERS = {"EXPERIENCE", "SKILLS", "EDUCATION", "PROJECTS", "CERTIFICATIONS"}

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            if not line.strip():
                pdf.ln(2)
                i += 1
                continue

            stripped = line.strip()

            # Name — first non-empty line
            if i == 0 or (i < 3 and len(stripped) < 40 and stripped.isupper() is False
                          and not stripped.startswith(("-", "•"))):
                pdf.set_font("Helvetica", style="B", size=14)
                pdf.cell(0, 8, stripped, ln=True)
                pdf.set_font("Helvetica", size=9)
                i += 1
                continue

            # Contact/Education header lines (lines 1-3)
            if i < 4 and ("|" in stripped or "Phone" in stripped or "Email" in stripped
                          or "Education" in stripped or "LinkedIn" in stripped):
                pdf.set_font("Helvetica", size=9)
                pdf.multi_cell(0, 5, stripped)
                i += 1
                continue

            # Section headers like EXPERIENCE, SKILLS
            if stripped.upper() in SECTION_HEADERS or (
                stripped.isupper() and len(stripped) < 30
            ):
                pdf.ln(3)
                pdf.set_font("Helvetica", style="B", size=11)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(0, 6, stripped, ln=True, fill=True)
                pdf.set_font("Helvetica", size=10)
                i += 1
                continue

            # Company name — bold, no indent, followed by role on next line
            if (not stripped.startswith(("-", "•"))
                    and len(stripped) < 60
                    and i + 1 < len(lines)
                    and any(kw in lines[i + 1].lower() for kw in
                            ["manager", "engineer", "intern", "analyst", "lead", "director", "head"])):
                pdf.ln(2)
                pdf.set_font("Helvetica", style="B", size=10)
                pdf.cell(0, 6, stripped, ln=True)
                pdf.set_font("Helvetica", size=10)
                i += 1
                continue

            # Date ranges inline
            if "|" in stripped and any(
                yr in stripped for yr in ["20", "19", "Present", "Jan", "Feb", "Mar",
                                          "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                          "Oct", "Nov", "Dec"]
            ):
                pdf.set_font("Helvetica", style="I", size=9)
                pdf.cell(0, 5, stripped, ln=True)
                pdf.set_font("Helvetica", size=10)
                i += 1
                continue

            # Sub-headers like "Product Improvements:", "Organic Traffic Projects:"
            if stripped.endswith(":") and len(stripped) < 60 and not stripped.startswith("-"):
                pdf.set_font("Helvetica", style="B", size=10)
                pdf.cell(0, 5, stripped, ln=True)
                pdf.set_font("Helvetica", size=10)
                i += 1
                continue

            # Bullet points
            if stripped.startswith(("-", "•")):
                bullet_text = stripped.lstrip("-• ").strip()
                pdf.set_x(20)
                pdf.set_font("Helvetica", size=10)
                pdf.cell(4, 5, "-")
                pdf.multi_cell(0, 5, bullet_text)
                i += 1
                continue

            # Skills lines (bold label: content)
            if ":" in stripped and not stripped.startswith("-"):
                parts = stripped.split(":", 1)
                pdf.set_font("Helvetica", style="B", size=10)
                pdf.cell(pdf.get_string_width(parts[0] + ": "), 5, parts[0] + ":")
                pdf.set_font("Helvetica", size=10)
                pdf.multi_cell(0, 5, parts[1].strip())
                i += 1
                continue

            # Default
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 5, stripped)
            i += 1

        pdf.output(str(output_path))
        return output_path

    def get_optimized_resume_path(self, job_id: str, jd_text: str,
                                   job_title: str, company: str, provided_text: str = "") -> Path:
        output_dir = Path(__file__).parent / "optimized_resumes"
        output_dir.mkdir(exist_ok=True)
        prefix = "delegated" if provided_text else "resume"
        output_path = output_dir / f"{prefix}_{job_id}.pdf"

        if output_path.exists():
            return output_path  # already generated for this job

        if provided_text:
            optimized_text = provided_text
        else:
            optimized_text = self.optimize(jd_text, job_title, company)

        self.save_as_pdf(optimized_text, output_path)
        return output_path

    def extract_companies(self) -> list[str]:
        """Extract past/current employer names from the resume using Claude."""
        if not self.client:
            # Fallback: cannot extract without LLM, return empty list
            return []

        try:
            resume_text = self.read_resume()
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": f"""Extract all company/employer names from this resume.
Return ONLY a JSON array of strings, e.g. ["Company A", "Company B"].
No explanations, no markdown.

Resume:
{resume_text}"""}]
            )
            import json
            return json.loads(message.content[0].text)
        except Exception:
            return []

    def get_match_score(self, jd_text: str) -> dict:
        if not self.client:
            # Fallback: cannot score without LLM, return a neutral score
            return {
                "score": 100,
                "matching_skills": [],
                "missing_skills": [],
                "recommendation": "Internal scoring unavailable (No API key). Proceeding with application."
            }

        try:
            resume_text = self.read_resume()
            prompt = f"""Analyze how well this resume matches the job description.

JD:
<jd>{jd_text}</jd>

Resume:
<resume>{resume_text}</resume>

Return a JSON object with:
- score: integer 0-100
- matching_skills: list of skills/keywords present in both
- missing_skills: list of important JD keywords missing from resume
- recommendation: one sentence on fit

Return ONLY valid JSON, no markdown."""

            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            import json
            return json.loads(message.content[0].text)
        except Exception:
            return {"score": 100, "recommendation": "Error during internal scoring."}
