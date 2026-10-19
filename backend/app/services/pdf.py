"""Render resume content as a PDF that ATS software can read.

What makes a resume PDF machine-readable is mostly what it avoids: one
column, real text (not an image), no tables or text boxes, standard section
headings, standard fonts. That's all this does. The ATS check
(app/services/ats.py) proves it by reading the text back out.
"""

import unicodedata

from fpdf import FPDF

from app.schemas import ResumeContent

# ponytail: built-in PDF fonts cover Latin-1 only, so accented Latin letters
# work but e.g. Chinese names become "?". Bundle a Unicode TTF (add_font) if
# that matters.
_PLAIN = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2022": "-", "\u2026": "...", "\u2192": "->", "\u2190": "<-",
    "\u2248": "~", "\u2264": "<=", "\u2265": ">=", "\u00a0": " ",
}


def _plain(ch: str) -> str:
    if ch in _PLAIN:
        return _PLAIN[ch]
    if ord(ch) < 256:
        return ch
    category = unicodedata.category(ch)
    # By category, not one by one: every dash (non-breaking hyphen U+2011, en
    # and em dashes...) and every space (narrow no-break U+202F, thin...).
    if category == "Pd":
        return "-"
    if category == "Zs":
        return " "
    # Ligatures and the like have a plain equivalent (e.g. "ﬁ" is "fi").
    decomposed = unicodedata.normalize("NFKD", ch)
    return decomposed if all(ord(c) < 256 for c in decomposed) else "?"


def latin1(text: str) -> str:
    """Text the built-in fonts can draw: look-alikes swapped for plain
    characters, "?" only for what has no plain equivalent."""
    return "".join(_plain(ch) for ch in text)


class _Resume(FPDF):
    LINE = 5  # mm per line of body text

    def heading(self, title: str) -> None:
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)

    def body(self, text: str, style: str = "") -> None:
        self.set_font("Helvetica", style, 10)
        # Left-aligned: fpdf2 justifies by default, which stretches the spaces.
        self.multi_cell(0, self.LINE, latin1(text), align="L", new_x="LMARGIN", new_y="NEXT")

    def title_line(self, left: str, right: str = "") -> None:
        """Bold title on the left, dates on the right. A title too long for the
        space left of the dates wraps onto more lines instead of running into
        them."""
        width = self.w - self.l_margin - self.r_margin
        right = latin1(right)
        self.set_font("Helvetica", "", 10)
        right_width = self.get_string_width(right) + 4 if right else 0
        # Start a new page now rather than have the title and its dates split
        # across two pages.
        if self.get_y() + 2 * self.LINE > self.page_break_trigger:
            self.add_page()
        top = self.get_y()
        self.set_font("Helvetica", "B", 10)
        self.multi_cell(
            width - right_width, self.LINE, latin1(left), align="L",
            new_x="LMARGIN", new_y="NEXT",
        )
        bottom = self.get_y()
        if right:
            self.set_xy(self.l_margin + width - right_width, top)
            self.set_font("Helvetica", "", 10)
            self.cell(right_width, self.LINE, right, align="R")
        self.set_xy(self.l_margin, bottom)

    def bullets(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 10)
        for item in items:
            self.set_x(self.l_margin + 3)
            self.multi_cell(
                0, self.LINE, "- " + latin1(item), align="L", new_x="LMARGIN", new_y="NEXT"
            )


def render_pdf(content: ResumeContent) -> bytes:
    pdf = _Resume(format="Letter")
    pdf.set_margins(18, 15, 18)
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()

    if content.full_name:
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 9, latin1(content.full_name), new_x="LMARGIN", new_y="NEXT")
    if content.contact:
        pdf.body(content.contact)

    if content.summary:
        pdf.heading("Summary")
        pdf.body(content.summary)
    if content.skills:
        pdf.heading("Skills")
        pdf.body(", ".join(content.skills))
    if content.experience:
        pdf.heading("Experience")
        for exp in content.experience:
            pdf.title_line(f"{exp.title}, {exp.company}", exp.dates)
            pdf.bullets(exp.bullets)
            pdf.ln(1)
    if content.projects:
        pdf.heading("Projects")
        for proj in content.projects:
            pdf.title_line(proj.name)
            if proj.description:
                pdf.body(proj.description)
            if proj.technologies:
                pdf.body("Technologies: " + ", ".join(proj.technologies), style="I")
            pdf.bullets(proj.bullets)
            pdf.ln(1)
    if content.education:
        pdf.heading("Education")
        for edu in content.education:
            name = f"{edu.degree}, {edu.school}" if edu.degree else edu.school
            pdf.title_line(name, edu.dates)
            pdf.bullets(edu.details)

    return bytes(pdf.output())
