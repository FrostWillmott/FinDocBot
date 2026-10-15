"""Synthetic annual reports and questions for the retrieval evaluation.

The corpus and every question are written by the project, not independent of
it, so results on it are indicative only; the decision to rely on a reranker
needs real documents (see evals/README.md). What the corpus does is isolate the
situations that matter for financial reports: many reports with the same
structure, the same company across fiscal years, and sections that never name
the company or the year.

Everything is deterministic (fixed seed). Gold labels are figures that appear
exactly once in the whole corpus, so a hit can be checked by string match.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

SEED = 20261015
YEARS = (2023, 2024, 2025)
QUESTIONS_PER_CATEGORY = 8
DEFAULT_QUESTIONS = Path("evals/questions/synthetic.jsonl")
DEFAULT_PDF_DIR = Path("evals/data/synthetic")

# Question categories, by what makes the target chunk easy or hard to find.
EXACT = "exact_wording"
PARAPHRASE = "paraphrase"
YEAR_ONLY = "year_only_context"
NO_CONTEXT = "no_company_or_year"
TOPICAL = "topical"
CATEGORIES = (EXACT, PARAPHRASE, YEAR_ONLY, NO_CONTEXT, TOPICAL)


@dataclass(frozen=True)
class Profile:
    """A fictional company: its name, segments, a sensitivity and claims."""

    name: str
    segments: tuple[str, str]
    sensitivity: str
    claims: tuple[str, str, str]

    @property
    def slug(self) -> str:
        """File-name friendly company name."""
        return self.name.lower().replace(" ", "-")


PROFILES = (
    Profile(
        "Northwind Freight",
        ("Road haulage", "Ocean freight"),
        "a 10% rise in diesel prices",
        (
            "a customs classification dispute in Rotterdam",
            "a warehouse lease claim in Gdansk",
            "a cargo damage suit in Mombasa",
        ),
    ),
    Profile(
        "Halcyon Foods",
        ("Snacks", "Beverages"),
        "a 10% rise in cocoa and sugar costs",
        (
            "a labelling investigation in Lyon",
            "a distributor termination claim in Osaka",
            "a recall liability suit in Dallas",
        ),
    ),
    Profile(
        "Brightwater Utilities",
        ("Water services", "Power generation"),
        "a 10% shortfall in reservoir inflows",
        (
            "a water rights appeal in Fresno",
            "a tariff refund claim in Leeds",
            "a pipeline easement dispute in Calgary",
        ),
    ),
    Profile(
        "Kestrel Semiconductors",
        ("Automotive chips", "Industrial chips"),
        "a 10% fall in wafer yields",
        (
            "a patent infringement claim in Munich",
            "an export licence review in Austin",
            "a supplier price dispute in Hsinchu",
        ),
    ),
    Profile(
        "Marlowe Insurance",
        ("Property cover", "Casualty cover"),
        "a 10% increase in catastrophe claims",
        (
            "a reserve adequacy inquiry in Zurich",
            "a policyholder class action in Phoenix",
            "a reinsurance recovery dispute in Bermuda",
        ),
    ),
    Profile(
        "Orchard Row Retail",
        ("Stores", "Online"),
        "a 10% drop in footfall",
        (
            "a lease guarantee claim in Glasgow",
            "a data protection inquiry in Dublin",
            "a supplier insolvency claim in Porto",
        ),
    ),
)


@dataclass(frozen=True)
class Facts:
    """The figures of one report, as they are printed in it."""

    revenue: str
    net_profit: str
    operating_margin: str
    dividend: str
    operating_cash_flow: str
    cash: str
    net_debt: str
    segment_a: str
    segment_b: str
    claim: str
    sensitivity_impact: str
    guidance: str
    capex: str


@dataclass(frozen=True)
class Report:
    """One synthetic annual report."""

    profile: Profile
    year: int
    facts: Facts
    claim_subject: str
    sections: tuple[tuple[str, str], ...]

    @property
    def filename(self) -> str:
        """PDF file name, e.g. ``northwind-freight-2024.pdf``."""
        return f"{self.profile.slug}-{self.year}.pdf"


@dataclass(frozen=True)
class Question:
    """A question, the report that answers it and the figure that proves it."""

    id: str
    category: str
    question: str
    document: str
    gold: str


def _usd(value: int) -> str:
    return f"USD {value:,} million"


class _Figures:
    """Draws money figures that never repeat anywhere in the corpus."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used: set[str] = set()

    def money(self, low: int, high: int) -> str:
        """Return a unique ``USD n million`` string with n in [low, high]."""
        while True:
            figure = _usd(self._rng.randint(low, high))
            if figure not in self._used:
                self._used.add(figure)
                return figure


def _amount(figure: str) -> int:
    return int(
        figure.removeprefix("USD ").removesuffix(" million").replace(",", "")
    )


def _facts(rng: random.Random, figures: _Figures) -> Facts:
    revenue = figures.money(900, 3900)
    scale = _amount(revenue)
    low, high = max(scale // 10, 90), max(scale // 3, 190)
    segment_a = figures.money(scale * 4 // 10, scale * 6 // 10)
    return Facts(
        revenue=revenue,
        net_profit=figures.money(scale // 20, scale // 7),
        operating_margin=f"{rng.uniform(7, 22):.1f}%",
        dividend=f"USD {rng.uniform(0.2, 2.4):.2f}",
        operating_cash_flow=figures.money(low, high),
        cash=figures.money(120, 1500),
        net_debt=figures.money(80, 1200),
        segment_a=segment_a,
        segment_b=figures.money(scale * 3 // 10, scale * 5 // 10),
        claim=figures.money(12, 190),
        sensitivity_impact=figures.money(15, 95),
        guidance=f"{rng.randint(2, 6)}% to {rng.randint(7, 11)}%",
        capex=figures.money(60, 400),
    )


_LETTER_OPENERS = (
    "{name} had a year of steady execution in fiscal {year}.",
    "For {name}, fiscal {year} paired cost control with investment.",
    "{name} entered fiscal {year} with a clear plan and delivered most of it.",
)
_LETTER_CLOSERS = (
    "We thank our employees, customers and shareholders for their trust.",
    "The Board is grateful for the commitment shown across the group.",
    "We remain focused on returns for shareholders over the long term.",
)
_LETTER_BODY = (
    "Management concentrated on service quality, cost discipline and the "
    "strength of the balance sheet rather than on headline growth. The "
    "executive committee reviewed capital allocation every quarter and "
    "kept investment within the limits approved by the Board. Safety, "
    "compliance and the retention of skilled staff remained the first "
    "priorities of every business unit during the year."
)
_HIGHLIGHTS_NOTE = (
    "Revenue is recognised when control of goods or services passes to the "
    "customer. Net profit is stated after tax and after the share of "
    "non-controlling interests. All figures are in millions of US dollars "
    "unless stated otherwise, and comparatives have been restated where "
    "accounting policies changed. The operating margin is operating profit "
    "divided by total revenue."
)
_CASH_NOTE = (
    "Cash flow is reported on the indirect method. Capital expenditure, "
    "interest paid and dividends are shown within investing and financing "
    "activities. The Group keeps committed credit facilities in place and "
    "tests its liquidity against a severe but plausible downside scenario "
    "each half year. Net debt is borrowings less cash and cash equivalents."
)
_SEGMENT_NOTE = (
    "Segment results are reported on the basis used by the chief operating "
    "decision maker. Sales between segments are priced at arm's length and "
    "eliminated on consolidation. Central costs are allocated to segments "
    "in proportion to revenue, and segment assets are reviewed each "
    "quarter together with the capital employed."
)
_RISK_NOTE = (
    "The risk management framework is overseen by the Audit Committee, "
    "which reviews the principal risks twice a year. Mitigating actions are "
    "assigned to named executives and tracked to completion. The Group "
    "maintains insurance for the main operational hazards, and provisions "
    "are recorded where an outflow is probable and can be estimated."
)
_OUTLOOK_NOTE = (
    "This outlook contains forward-looking statements. They reflect "
    "management's current expectations and are subject to risks and "
    "uncertainties that could cause actual results to differ materially. "
    "The Group does not undertake to update these statements except as "
    "required by applicable regulation or the listing rules."
)


def _sections(
    rng: random.Random, profile: Profile, year: int, facts: Facts, claim: str
) -> tuple[tuple[str, str], ...]:
    name = profile.name
    seg_a, seg_b = profile.segments
    opener = rng.choice(_LETTER_OPENERS).format(name=name, year=year)
    letter = f"{opener} {_LETTER_BODY} {rng.choice(_LETTER_CLOSERS)}"
    highlights = (
        f"{name} reported total revenue of {facts.revenue} for fiscal "
        f"{year}. Net profit was {facts.net_profit}, and the operating "
        f"margin was {facts.operating_margin}. The Board proposed a "
        f"dividend of {facts.dividend} per share, in line with the stated "
        f"payout policy. {_HIGHLIGHTS_NOTE}"
    )
    cash_flow = (
        f"In fiscal {year}, the Group generated operating cash flow of "
        f"{facts.operating_cash_flow}. Cash and cash equivalents at year "
        f"end stood at {facts.cash}, and net debt was {facts.net_debt}. "
        f"{_CASH_NOTE}"
    )
    segments = (
        f"The {seg_a} segment reported revenue of {facts.segment_a}, and "
        f"the {seg_b} segment reported revenue of {facts.segment_b}. "
        f"{_SEGMENT_NOTE}"
    )
    risks = (
        f"The most significant sensitivity is {profile.sensitivity}, which "
        f"would reduce operating profit by about {facts.sensitivity_impact}. "
        f"The Group also disclosed {claim}, with {facts.claim} at stake; "
        f"management considers the claim to be without merit. {_RISK_NOTE}"
    )
    outlook = (
        f"{name} expects revenue growth of {facts.guidance} next year and "
        f"plans capital expenditure of {facts.capex}. Guidance assumes "
        "stable exchange rates, no major acquisitions and normal demand "
        f"conditions across the Group's markets. {_OUTLOOK_NOTE}"
    )
    return (
        ("Section 1. Letter to Shareholders", letter),
        ("Section 2. Financial Highlights", highlights),
        ("Section 3. Cash Flow and Balance Sheet", cash_flow),
        ("Section 4. Segment Results", segments),
        ("Section 5. Risk Factors", risks),
        ("Section 6. Outlook", outlook),
    )


def build_reports() -> list[Report]:
    """Generate every report of the corpus, deterministically."""
    rng = random.Random(SEED)
    figures = _Figures(rng)
    reports = []
    for profile in PROFILES:
        for year, claim in zip(YEARS, profile.claims, strict=True):
            facts = _facts(rng, figures)
            sections = _sections(rng, profile, year, facts, claim)
            reports.append(Report(profile, year, facts, claim, sections))
    return reports


def render_pdf(report: Report) -> bytes:
    """Render a report as a small multi-section PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    left = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(
        0, 9, f"{report.profile.name} - Annual Report {report.year}", **left
    )
    pdf.ln(3)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(
        0,
        6,
        "Synthetic document for retrieval evaluation. Fictional company; "
        "all figures are invented.",
        **left,
    )
    pdf.ln(7)
    for title, body in report.sections:
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 8, title, **left)
        pdf.ln(2)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, body, **left)
        pdf.ln(7)
    return bytes(pdf.output())


def _asks(
    category: str, report: Report, index: int
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Two (question, gold) options for a category; the index picks one."""
    name, year, facts = report.profile.name, report.year, report.facts
    segment = report.profile.segments[index % 2]
    segment_figure = facts.segment_a if index % 2 == 0 else facts.segment_b
    if category == EXACT:
        return (
            (
                f"What was {name}'s total revenue in fiscal {year}?",
                facts.revenue,
            ),
            (
                f"What was the net profit of {name} in fiscal {year}?",
                facts.net_profit,
            ),
        )
    if category == PARAPHRASE:
        return (
            (
                f"How much did {name} bring in from sales during {year}?",
                facts.revenue,
            ),
            (
                f"What was {name}'s bottom line after tax in {year}?",
                facts.net_profit,
            ),
        )
    if category == YEAR_ONLY:
        return (
            (
                f"How much cash did {name} hold at the end of {year}?",
                facts.cash,
            ),
            (f"What was {name}'s net debt in {year}?", facts.net_debt),
        )
    if category == NO_CONTEXT:
        ask = f"What revenue did {name}'s {segment} segment report in {year}?"
        return ((ask, segment_figure), (ask, segment_figure))
    ask = f"How much is at stake in the {report.claim_subject}?"
    return ((ask, facts.claim), (ask, facts.claim))


def _questions_for(
    rng: random.Random, category: str, reports: list[Report]
) -> list[tuple[str, Report, str]]:
    """Pick the reports for a category and phrase one question for each."""
    picked = rng.sample(reports, QUESTIONS_PER_CATEGORY)
    out = []
    for index, report in enumerate(picked):
        question, gold = _asks(category, report, index)[index % 2]
        out.append((question, report, gold))
    return out


def build_questions(reports: list[Report]) -> list[Question]:
    """Return the frozen question set for the corpus."""
    rng = random.Random(SEED + 1)
    questions = []
    for category in CATEGORIES:
        for question, report, gold in _questions_for(rng, category, reports):
            questions.append(
                Question(
                    f"q{len(questions) + 1:02d}",
                    category,
                    question,
                    report.filename,
                    gold,
                )
            )
    return questions


def write_questions(questions: list[Question], path: Path) -> None:
    """Write the questions as JSON lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(asdict(q), ensure_ascii=False) for q in questions)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_questions(path: Path) -> list[Question]:
    """Read questions from a JSON lines file."""
    rows = (json.loads(line) for line in path.read_text().splitlines() if line)
    return [Question(**row) for row in rows]


def main() -> None:
    """Write the PDFs and the question file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = parser.parse_args()
    reports = build_reports()
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        (args.pdf_dir / report.filename).write_bytes(render_pdf(report))
    questions = build_questions(reports)
    write_questions(questions, args.questions)
    print(f"{len(reports)} reports -> {args.pdf_dir}")
    print(f"{len(questions)} questions -> {args.questions}")


if __name__ == "__main__":
    main()
