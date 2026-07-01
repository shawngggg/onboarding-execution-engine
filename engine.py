from enum import Enum

VALID_PRODUCTS = [
    "cash_equities",
    "mutual_funds",
    "fixed_income",
    "options",
    "margin",
    "alternatives_futures",
]

class Disposition(Enum):
    CLEAR = "clear"
    REFER = "refer"
    ESCALATE = "escalate"
    BLOCK = "block"

class Decision:
    def __init__(self, disposition, reason, rule_id, required_documents=None):
        self.disposition = disposition
        self.reason = reason
        self.rule_id = rule_id
        self.required_documents = required_documents or []

class ProductExperience:
    def __init__(self, years=0, trades_per_year=0):
        self.years = years
        self.trades_per_year = trades_per_year


class Case:
    def __init__(
        self,
        # --- identity basics ---
        name,
        date_of_birth,          # store the source fact, not age
        country_of_birth,
        # --- status (self-attested facts) ---
        citizenship_status,     #"citizen" | "green_card_ | "non_resident_alien"
        # --- contact ---
        residential_address,
        mailing_address,
        # --- economic profile ---
        occupation,
        employer,
        source_of_funds,
        source_of_wealth,
        investment_experience,   # dict: product name -> ProductExperience
        account_purpose,
        is_broker_dealer,        # flips suitability/conduct analysis
    ):
        self.name = name
        self.date_of_birth = country_of_birth
        self.citizenship_status = citizenship_status
        self.residential_address = residential_address
        self.mailing_address = mailing_address
        self.occupation = occupation
        self.employer = employer
        self.source_of_funds = source_of_funds
        self.source_of_wealth = source_of_wealth
        self.investment_experience = investment_experience
        self.account_purpose = account_purpose
        self.is_broker_dealer = is_broker_dealer

def evaluate(case):
    if case.citizenship_status == "non_resident_alien":
        return Decision(
            disposition=Disposition.REFER,
            reason="Non-resident alien requires additional CIP documentation",
            rule_id="CIP-001",
            required_documents=["passport", "W-8BEN"],
        )
    return Decision(
        disposition=Disposition.CLEAR,
        reason="US person; no additional CIP documentation required",
        rule_id="CIP-000",
        required_documents=[],
    )

# --- try it out ---
maria = Case(
    name="Maria Chen",
    date_of_birth="1985-03-12",
    country_of_birth="United States",
    citizenship_status="green_card",
    residential_address="1200 Oak St, Salt Lake City, UT 84101",
    mailing_address="1200 Oak St, Salt Lake City, UT 84101",
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

maria_decision = evaluate(maria)
print(maria.name, "->", maria_decision.disposition)
print("   reason:", maria_decision.reason)
print("   rule:", maria_decision.rule_id)
print("   documents needed:", maria_decision.required_documents)
print()

kenji_decision = evaluate(kenji)
print(kenji.name, "->", kenji_decision.disposition)
print("   reason:", kenji_decision.reason)
print("   rule:", kenji_decision.rule_id)
print("   documents needed:", kenji_decision.required_documents)