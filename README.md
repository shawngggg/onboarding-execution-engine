Compliance Onboarding Execution Engine
A policy-as-code decisioning engine for account onboarding. It applies KYC, CIP, sanctions, and suitability
rules to an applicant and returns an explainable decision: the disposition, the rule and version that made
it, the regulation behind it, and the documents still needed.
Live demo
Open the live demo
Source code
View on GitHub
Version
v2, policy
2026.09
Author
Shawn Ghodrati
What's new in v2
• Every rule carries a version, an effective date, an optional expiry date, and a cited regulatory source.
• The engine applies only the rule versions in force on the evaluation date, so policy changes never rewrite past
decisions.
• Every decision writes an audit record with the policy and rule version, source, inputs, and any warnings.
• OFAC-001 has two versions around the July 1, 2025 termination of the U.S. Syria sanctions program. The same
applicant is escalated in June 2025 and cleared in July 2025.
• Fix: non-resident aliens are no longer referred for a missing U.S. state.
Live demo
The engine runs in the browser at https://shawngggg.github.io/onboarding-execution-engine/. The page has five
working views:
View
What it does
Live intake
Enter an applicant with field-level validation, then run the decision.
Sample cases
Six prepared applicants, each exercising a different branch of the engine.
Versioning
The same applicant evaluated on two dates, before and after a policy change.
Rule library
Every rule with its version, effective dates, condition, and cited source.
Audit log
The full record behind every decision made in the session, copyable as JSON.
How a decision is made
Every application follows the same sequence, so every outcome can be traced and reproduced.
Step
What happens
1. Completeness gate
Required identifying fields are checked first. An incomplete application is referred (VAL-001)
and never reaches a clear.
2. Rules in force
Only the rule versions in force on the evaluation date are loaded, in precedence order.
3. First match wins
Rules are tested top to bottom. The first rule whose condition matches sets the disposition.
4. Default clear
If no rule matches, the application clears under standard onboarding (CIP-000).
Page 1
Compliance Onboarding Execution Engine  |  Shawn Ghodrati  |  github.com/shawngggg
Compliance Onboarding Execution Engine  |  Shawn Ghodrati  |  github.com/shawngggg Page 2
