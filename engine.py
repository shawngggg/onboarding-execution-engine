"""
Compliance Onboarding Execution Engine — v2
--------------------------------------------
A policy-as-code decisioning engine for account onboarding.

Design principles carried through the build:
  - Collect facts, compute judgments (e.g. age is derived from date_of_birth).
  - Status vs. evidence stay separate (what's claimed vs. what's proven).
  - Rules live as DATA (the RULES library), not welded into code.
  - The evaluator is generic: it reads any rule and applies it. Rules grow;
    the engine does not.
  - Defensive by default: a bad rule warns and is skipped, never crashes
    the whole engine.

New in v2:
  - Every rule carries a version, an effective date, an optional expiry date,
    and a cited source. The engine applies only the rule versions in force on
    the evaluation date, so policy changes are dated, not overwritten.
  - Every decision produces an audit record: which policy version and rule
    version decided it, the cited source, the inputs it saw, the evaluation
    date, and any warnings raised along the way. Records are written to
    audit_log.jsonl.
  - Warnings are captured in the audit record instead of printed and lost.
  - Fix: non-resident aliens are no longer referred for a missing US state.

This is a learning / automation project, not production compliance software.
Rule content and citations are illustrative and would require review by
qualified counsel.
"""

import json
from datetime import date, datetime, timezone
from enum import Enum


POLICY_VERSION = "2026.09"


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class Disposition(Enum):
    CLEAR = "clear"
    REFER = "refer"
    ESCALATE = "escalate"
    BLOCK = "block"


class Decision:
    """The output 'folder': a verdict plus the reasoning and evidence behind it."""
    def __init__(self, disposition, reason, rule_id, source,
                 rule_version="1", required_documents=None):
        self.disposition = disposition
        self.reason = reason
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.source = source
        self.required_documents = required_documents or []


class ProductExperience:
    """Experience with a single investment product — objective, not adjectives."""
    def __init__(self, years=0, trades_per_year=0):
        self.years = years
        self.trades_per_year = trades_per_year


# Single source of truth for the products the suitability layer knows about.
VALID_PRODUCTS = [
    "cash_equities",
    "mutual_funds",
    "fixed_income",
    "options",
    "margin",
    "alternatives_futures",
]


class Case:
    """The input 'folder': the raw stated facts about a subject being onboarded."""
    def __init__(
        self,
        # --- identity basics ---
        name,
        date_of_birth,          # store the source fact; age is computed
        country_of_birth,
        # --- status (self-attested) ---
        citizenship_status,     # "citizen" | "green_card" | "non_resident_alien"
        # --- contact ---
        residential_address,
        mailing_address,
        state_of_residence,     # 2-letter state, drives age-of-majority
        # --- economic profile ---
        occupation,
        employer,
        source_of_funds,
        source_of_wealth,
        investment_experience,  # dict: product name -> ProductExperience
        account_purpose,
        is_broker_dealer,
    ):
        self.name = name
        self.date_of_birth = date_of_birth
        self.country_of_birth = country_of_birth
        self.citizenship_status = citizenship_status
        self.residential_address = residential_address
        self.mailing_address = mailing_address
        self.state_of_residence = state_of_residence
        self.occupation = occupation
        self.employer = employer
        self.source_of_funds = source_of_funds
        self.source_of_wealth = source_of_wealth
        self.investment_experience = investment_experience or {}
        self.account_purpose = account_purpose
        self.is_broker_dealer = is_broker_dealer

    # --- computed determinations (judgments, not stored facts) ---

    def age_on(self, as_of):
        """Age in years on a given date, computed from date_of_birth."""
        try:
            born = date.fromisoformat(self.date_of_birth)
        except (ValueError, TypeError):
            return None
        return as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))

    @property
    def age(self):
        return self.age_on(date.today())

    @property
    def is_us_person(self):
        """US person = citizen OR green-card holder (broader than citizen)."""
        return self.citizenship_status in ("citizen", "green_card")

    def snapshot(self):
        """The facts the engine saw, captured for the audit record."""
        facts = {k: v for k, v in vars(self).items() if k != "investment_experience"}
        facts["investment_experience"] = {
            p: {"years": e.years, "trades_per_year": e.trades_per_year}
            for p, e in self.investment_experience.items()
        }
        return facts


# ---------------------------------------------------------------------------
# Age of majority by state (the states that differ from 18)
# ---------------------------------------------------------------------------

AGE_OF_MAJORITY = {
    "AL": 19,
    "NE": 19,
    "MS": 21,
}
DEFAULT_AGE_OF_MAJORITY = 18


def age_of_majority(state):
    return AGE_OF_MAJORITY.get(state, DEFAULT_AGE_OF_MAJORITY)


# ---------------------------------------------------------------------------
# The rule library (policy-as-code)
#
# Each rule carries its own condition (field / operator / value), its own
# outcome (disposition, reason, required_documents), and its own provenance:
#   version         — bumped whenever the rule's logic changes
#   effective_date  — first date this version is in force
#   expiry_date     — optional; the version stops applying on this date
#   source          — the regulation or policy the rule implements
#
# To change policy, add a new version with a new effective date rather than
# editing the old one. Past decisions stay reproducible.
#
# Rules are evaluated top to bottom; the first match wins. Order therefore
# encodes precedence: identity/sanctions gate before suitability.
# ---------------------------------------------------------------------------

RULES = [
    # Sanctions, version 1: in force until the Syria program was terminated.
    # NOTE: country of birth is an illustrative proxy. Production screening
    # matches names against OFAC's SDN list and checks residence and
    # nationality in comprehensively sanctioned jurisdictions.
    {
        "rule_id": "OFAC-001",
        "version": "1",
        "effective_date": "2024-01-01",
        "expiry_date": "2025-07-01",
        "source": "OFAC sanctions programs: Iran (31 CFR Part 560), North Korea "
                  "(31 CFR Part 510), Syria (31 CFR Part 542), Cuba (31 CFR Part 515)",
        "field": "country_of_birth",
        "operator": "in",
        "value": ["Iran", "North Korea", "Syria", "Cuba"],
        "disposition": Disposition.ESCALATE,
        "reason": "Country of birth in sanctioned jurisdiction; escalate for sanctions review",
        "required_documents": ["enhanced_due_diligence_review"],
    },
    # Sanctions, version 2: Syria removed. E.O. 14312 terminated the Syria
    # sanctions program effective July 1, 2025; OFAC removed 31 CFR Part 542
    # on August 26, 2025. Targeted Syria-related designations still apply
    # through list-based screening.
    {
        "rule_id": "OFAC-001",
        "version": "2",
        "effective_date": "2025-07-01",
        "source": "OFAC sanctions programs: Iran (31 CFR Part 560), North Korea "
                  "(31 CFR Part 510), Cuba (31 CFR Part 515); Syria program "
                  "terminated by E.O. 14312",
        "field": "country_of_birth",
        "operator": "in",
        "value": ["Iran", "North Korea", "Cuba"],
        "disposition": Disposition.ESCALATE,
        "reason": "Country of birth in sanctioned jurisdiction; escalate for sanctions review",
        "required_documents": ["enhanced_due_diligence_review"],
    },
    {
        "rule_id": "CIP-002",
        "version": "1",
        "effective_date": "2024-01-01",
        "source": "State Uniform Transfers/Gifts to Minors Acts (UTMA/UGMA); "
                  "state age-of-majority statutes",
        "field": "is_minor",              # computed field (see resolve_field)
        "operator": "equals",
        "value": True,
        "disposition": Disposition.REFER,
        "reason": "Subject is below the age of majority for their state; custodial account required",
        "required_documents": ["UTMA_UGMA_custodial_setup", "custodian_identification"],
    },
    {
        "rule_id": "CIP-001",
        "version": "1",
        "effective_date": "2024-01-01",
        "source": "31 CFR 1023.220 (broker-dealer CIP); IRS Form W-8BEN "
                  "(26 CFR 1.1441-1)",
        "field": "citizenship_status",
        "operator": "equals",
        "value": "non_resident_alien",
        "disposition": Disposition.REFER,
        "reason": "Non-resident alien requires additional CIP documentation",
        "required_documents": ["passport", "W-8BEN"],
    },
]

# Sources for the engine's built-in outcomes (not rule-library entries).
COMPLETENESS_SOURCE = ("31 CFR 1023.220(a)(2) (minimum CIP identifying "
                       "information: name, date of birth, address)")
DEFAULT_CLEAR_SOURCE = "31 CFR 1023.220 (CIP); FINRA Rule 2090 (Know Your Customer)"


def active_rules(as_of):
    """
    Return the rule versions in force on the evaluation date, preserving the
    library's precedence order. If more than one version of a rule is in
    force, the highest version wins.
    """
    chosen = {}
    order = []
    for rule in RULES:
        start = date.fromisoformat(rule["effective_date"])
        end = rule.get("expiry_date")
        if start > as_of or (end and as_of >= date.fromisoformat(end)):
            continue
        rid = rule["rule_id"]
        if rid not in chosen:
            order.append(rid)
            chosen[rid] = rule
        elif int(rule["version"]) > int(chosen[rid]["version"]):
            chosen[rid] = rule
    return [chosen[rid] for rid in order]


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def resolve_field(case, field, as_of):
    """
    Read a field the rule names. Supports real attributes AND computed fields
    so rules can reason about derived facts (age, minority) without the engine
    hardcoding that logic per rule. Returns (found, value).
    """
    if field == "is_minor":
        a = case.age_on(as_of)
        if a is None:
            return True, None
        return True, a < age_of_majority(case.state_of_residence)

    if hasattr(case, field):
        return True, getattr(case, field)

    return False, None


def check_condition(case, rule, as_of, warnings):
    """
    Safely test one rule's condition against a case.
    Defensive: an unknown field or operator adds a warning to the audit trail
    and returns False (rule skipped) rather than crashing the whole engine.
    """
    found, case_value = resolve_field(case, rule["field"], as_of)
    if not found:
        warnings.append(f"rule {rule['rule_id']} v{rule['version']} references "
                        f"unknown field '{rule['field']}'; skipped")
        return False

    operator = rule["operator"]
    value = rule["value"]

    try:
        if operator == "equals":
            return case_value == value
        if operator == "not_equals":
            return case_value != value
        if operator == "in":
            return case_value in value
        if operator == "not_in":
            return case_value not in value
        if operator == "less_than":
            return case_value < value
        if operator == "greater_than_or_equal":
            return case_value >= value
    except TypeError:
        # e.g. comparing None < 18 — treat as non-match, don't crash.
        warnings.append(f"rule {rule['rule_id']} v{rule['version']} could not "
                        f"compare '{rule['field']}'; skipped")
        return False

    warnings.append(f"rule {rule['rule_id']} v{rule['version']} uses unknown "
                    f"operator '{operator}'; skipped")
    return False


# (attribute, label, applies_to) — applies_to decides whether the field is
# required for this case. A US state is only required for US residents.
REQUIRED_FIELDS = [
    ("name", "Name", lambda c: True),
    ("date_of_birth", "Date of birth", lambda c: True),
    ("country_of_birth", "Country of birth", lambda c: True),
    ("citizenship_status", "Citizenship status", lambda c: True),
    ("residential_address", "Residential address", lambda c: True),
    ("state_of_residence", "State of residence",
     lambda c: c.citizenship_status != "non_resident_alien"),
]


def missing_fields(case):
    """Return labels of required fields that are absent or blank."""
    missing = []
    for attr, label, applies_to in REQUIRED_FIELDS:
        if not applies_to(case):
            continue
        val = getattr(case, attr, None)
        if val is None or str(val).strip() in ("", "—"):
            missing.append(label)
    return missing


def evaluate(case, as_of=None, warnings=None):
    """
    Apply the rules in force on the evaluation date. A completeness gate runs
    first: incomplete data must never CLEAR, so a case missing any required
    field is REFERRED before any rule (or the default clear) is reached.
    First matching rule wins; if none match, default to a clean clear.
    """
    as_of = as_of or date.today()
    warnings = warnings if warnings is not None else []

    missing = missing_fields(case)
    if missing:
        return Decision(
            disposition=Disposition.REFER,
            reason="Incomplete application — required field(s) missing: "
                   + ", ".join(missing),
            rule_id="VAL-001",
            source=COMPLETENESS_SOURCE,
            required_documents=["completed_application"],
        )
    for rule in active_rules(as_of):
        if check_condition(case, rule, as_of, warnings):
            return Decision(
                disposition=rule["disposition"],
                reason=rule["reason"],
                rule_id=rule["rule_id"],
                rule_version=rule["version"],
                source=rule["source"],
                required_documents=rule["required_documents"],
            )
    return Decision(
        disposition=Disposition.CLEAR,
        reason="No matching rule; standard onboarding",
        rule_id="CIP-000",
        source=DEFAULT_CLEAR_SOURCE,
        required_documents=[],
    )


# ---------------------------------------------------------------------------
# Suitability layer (the brokerage-specific wedge)
#
# Separate from the CIP/sanctions gate above. Given an approved account, decide
# which products the subject is eligible to trade, based on product-level
# experience. Deliberately conservative, explainable, and cited.
# ---------------------------------------------------------------------------

SUITABILITY_REQUIREMENTS = {
    # product           -> (min_years, min_trades_per_year, source)
    "cash_equities":        (0, 0,  "FINRA Rule 2111 (suitability); Reg BI"),
    "mutual_funds":         (0, 0,  "FINRA Rule 2111 (suitability); Reg BI"),
    "fixed_income":         (0, 0,  "FINRA Rule 2111 (suitability); Reg BI"),
    "options":              (2, 10, "FINRA Rule 2360(b)(16) (options account approval)"),
    "margin":               (2, 10, "FINRA Rule 4210; Regulation T (12 CFR Part 220)"),
    "alternatives_futures": (3, 20, "FINRA Rule 2111 (suitability); firm policy"),
}


def assess_suitability(case):
    """
    Return a dict of product -> (eligible, reason, source).
    A product not present in the subject's experience is treated as no
    experience (the conservative default), never assumed.
    """
    results = {}
    for product in VALID_PRODUCTS:
        min_years, min_trades, source = SUITABILITY_REQUIREMENTS[product]
        exp = case.investment_experience.get(product, ProductExperience(0, 0))
        if exp.years >= min_years and exp.trades_per_year >= min_trades:
            if min_years == 0 and min_trades == 0:
                reason = "No experience threshold for this product"
            else:
                reason = (f"Meets threshold ({exp.years}y / {exp.trades_per_year} trades "
                          f"vs required {min_years}y / {min_trades})")
            results[product] = (True, reason, source)
        else:
            reason = (f"Below threshold ({exp.years}y / {exp.trades_per_year} trades "
                      f"vs required {min_years}y / {min_trades})")
            results[product] = (False, reason, source)
    return results


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

AUDIT_LOG_PATH = "audit_log.jsonl"


def build_audit_record(case, decision, as_of, warnings, suitability=None):
    """Everything needed to explain and reproduce a decision later."""
    record = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_date": as_of.isoformat(),
        "policy_version": POLICY_VERSION,
        "subject": case.name,
        "disposition": decision.disposition.value,
        "rule_id": decision.rule_id,
        "rule_version": decision.rule_version,
        "source": decision.source,
        "reason": decision.reason,
        "required_documents": decision.required_documents,
        "warnings": warnings,
        "inputs": case.snapshot(),
    }
    if suitability is not None:
        record["suitability"] = {
            p: {"eligible": e, "reason": r, "source": s}
            for p, (e, r, s) in suitability.items()
        }
    return record


def write_audit_record(record, path=AUDIT_LOG_PATH):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Runner — onboard a case, print the report, and log the audit record
# ---------------------------------------------------------------------------

def onboard(case, as_of=None, log=True):
    """Run the full onboarding assessment for one case."""
    as_of = as_of or date.today()
    warnings = []
    decision = evaluate(case, as_of, warnings)

    print(f"{case.name}  (age {case.age_on(as_of)}, {case.citizenship_status}, "
          f"born {case.country_of_birth})  evaluated {as_of.isoformat()}")
    print(f"  DECISION: {decision.disposition.name}")
    print(f"  reason:   {decision.reason}")
    print(f"  rule:     {decision.rule_id} v{decision.rule_version}")
    print(f"  source:   {decision.source}")
    print(f"  documents needed: {decision.required_documents or 'none'}")

    suitability = None
    # Suitability only matters if the subject wasn't referred out at CIP.
    if decision.disposition in (Disposition.CLEAR, Disposition.ESCALATE):
        suitability = assess_suitability(case)
        print("  suitability:")
        for product, (eligible, reason, _source) in suitability.items():
            mark = "eligible    " if eligible else "not eligible"
            print(f"    - {product:<22} {mark}  ({reason})")
    for w in warnings:
        print(f"  [warning] {w}")
    print()

    if log:
        write_audit_record(build_audit_record(case, decision, as_of, warnings, suitability))
    return decision


# ---------------------------------------------------------------------------
# Sample personas — exercise the different branches
# ---------------------------------------------------------------------------

def sample_cases():
    maria = Case(
        name="Maria Chen",
        date_of_birth="1985-03-12",
        country_of_birth="United States",
        citizenship_status="green_card",
        residential_address="1200 Oak St, Salt Lake City, UT 84101",
        mailing_address="1200 Oak St, Salt Lake City, UT 84101",
        state_of_residence="UT",
        occupation="Software Engineer",
        employer="Tech Corp",
        source_of_funds="Employment income",
        source_of_wealth="Salary and equity compensation",
        investment_experience={
            "cash_equities": ProductExperience(years=15, trades_per_year=50),
            "options": ProductExperience(years=5, trades_per_year=30),
        },
        account_purpose="Long-term investing",
        is_broker_dealer=False,
    )

    kenji = Case(
        name="Kenji Tanaka",
        date_of_birth="1979-08-22",
        country_of_birth="Japan",
        citizenship_status="non_resident_alien",
        residential_address="4-1 Chiyoda, Tokyo, Japan",
        mailing_address="4-1 Chiyoda, Tokyo, Japan",
        state_of_residence=None,
        occupation="Business Owner",
        employer="Tanaka Trading K.K.",
        source_of_funds="Business income",
        source_of_wealth="Ownership of trading company",
        investment_experience={
            "cash_equities": ProductExperience(years=20, trades_per_year=100),
        },
        account_purpose="Portfolio diversification",
        is_broker_dealer=False,
    )

    farid = Case(
        name="Farid Hosseini",
        date_of_birth="1980-05-01",
        country_of_birth="Iran",
        citizenship_status="citizen",
        residential_address="500 Main St, Salt Lake City, UT 84101",
        mailing_address="500 Main St, Salt Lake City, UT 84101",
        state_of_residence="UT",
        occupation="Physician",
        employer="Regional Hospital",
        source_of_funds="Employment income",
        source_of_wealth="Medical practice",
        investment_experience={
            "cash_equities": ProductExperience(years=8, trades_per_year=20),
        },
        account_purpose="Retirement investing",
        is_broker_dealer=False,
    )

    # A minor in Mississippi (age of majority 21) — trips the custodial rule.
    taylor = Case(
        name="Taylor Brooks",
        date_of_birth="2006-06-15",
        country_of_birth="United States",
        citizenship_status="citizen",
        residential_address="9 Elm St, Jackson, MS 39201",
        mailing_address="9 Elm St, Jackson, MS 39201",
        state_of_residence="MS",
        occupation="Student",
        employer="N/A",
        source_of_funds="Gift",
        source_of_wealth="Family gift",
        investment_experience={},
        account_purpose="Custodial savings",
        is_broker_dealer=False,
    )

    return [maria, kenji, farid, taylor]


def versioning_demo():
    """
    The same applicant, evaluated on two dates, gets two different answers —
    because the policy in force changed between them, not because anyone
    edited history.
    """
    layla = Case(
        name="Layla Haddad",
        date_of_birth="1988-11-02",
        country_of_birth="Syria",
        citizenship_status="citizen",
        residential_address="77 State St, Salt Lake City, UT 84111",
        mailing_address="77 State St, Salt Lake City, UT 84111",
        state_of_residence="UT",
        occupation="Architect",
        employer="Design Studio LLC",
        source_of_funds="Employment income",
        source_of_wealth="Salary",
        investment_experience={
            "cash_equities": ProductExperience(years=6, trades_per_year=12),
        },
        account_purpose="Long-term investing",
        is_broker_dealer=False,
    )
    print("-" * 70)
    print("VERSIONING DEMO — same applicant, two evaluation dates")
    print("-" * 70)
    onboard(layla, as_of=date(2025, 6, 1))   # OFAC-001 v1 in force
    onboard(layla, as_of=date(2025, 7, 1))   # OFAC-001 v2 in force


if __name__ == "__main__":
    print("=" * 70)
    print(f"ONBOARDING EXECUTION ENGINE — v2  (policy {POLICY_VERSION})")
    print("=" * 70)
    print()
    for case in sample_cases():
        onboard(case)
    versioning_demo()
    print(f"Audit records written to {AUDIT_LOG_PATH}")
