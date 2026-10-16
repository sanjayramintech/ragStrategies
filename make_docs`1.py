"""Creates the sample knowledge base in ./data (10 documents + metadata.json).

You can add your own .txt files to ./data too. If a file is not listed in
metadata.json it gets default metadata (department=General, doc_type=misc, year=0).
"""
import json
from pathlib import Path

DOCS = {
    "hr_leave_policy_2023.txt": (
        {"department": "HR", "doc_type": "policy", "year": 2023},
        """Nimbus Labs Leave Policy (2023 edition). Full-time employees receive 20 days of paid annual leave per calendar year. Unused annual leave cannot be carried over and expires on 31 December. Sick leave is capped at 10 days per year, and a medical certificate is required for any absence longer than 2 consecutive days. Parental leave is 12 weeks for primary caregivers. Leave requests must be submitted in the HRLegacy portal at least 3 working days in advance. Managers must approve or reject a request within 2 working days. Employees may take unpaid leave of up to 15 days with director approval. This edition has been superseded by the 2024 policy.""",
    ),
    "hr_leave_policy_2024.txt": (
        {"department": "HR", "doc_type": "policy", "year": 2024},
        """Nimbus Labs Leave Policy (2024 edition). Full-time employees receive 24 days of paid annual leave per calendar year. Up to 5 unused days can be carried over, but they expire on 31 March of the following year. Sick leave is 12 days per year, and a doctor's certificate is required after 3 consecutive days of absence. Parental leave is 16 weeks for primary caregivers and 6 weeks for secondary caregivers. Leave requests must be filed in the PeopleHub portal at least 5 working days in advance. Managers have 48 hours to respond to a request. Unpaid leave of up to 30 days is possible with director approval. The company observes 12 public holidays per year, and employees may swap up to 2 of them for floating holidays.""",
    ),
    "hr_remote_work_policy_2025.txt": (
        {"department": "HR", "doc_type": "policy", "year": 2025},
        """Remote and Hybrid Work Policy 2025. Employees follow a hybrid model with three office days per week, normally Tuesday to Thursday. Core collaboration hours are 11:00 to 16:00 IST, and employees must be reachable during this window. New remote workers receive a one-time home office setup allowance of 500 dollars. A monthly internet stipend of 40 dollars is paid with the regular payroll. Working from abroad is allowed for up to 30 days per calendar year and requires VP approval and a legal check on tax and visa implications. Company laptops are refreshed every 36 months. The corporate VPN is mandatory, and public Wi-Fi may only be used with the VPN enabled.""",
    ),
    "finance_q3_report_2024.txt": (
        {"department": "Finance", "doc_type": "report", "year": 2024},
        """Q3 2024 Financial Report. Revenue reached 12.4 million dollars, an increase of 18 percent over Q2. Gross margin improved to 71 percent thanks to lower support costs. Cloud infrastructure spending rose 22 percent, driven by the new analytics product and data egress charges. Customer churn fell to 3.1 percent from 4.0 percent in the previous quarter. Operating expenses were 8.9 million dollars, and headcount grew from 142 to 155. Enterprise customers contributed 64 percent of total revenue. The company ended the quarter with 21.5 million dollars in cash. Management plans to renegotiate cloud contracts in Q4 and aims to bring churn below 3 percent by mid 2025.""",
    ),
    "finance_expense_policy_2025.txt": (
        {"department": "Finance", "doc_type": "policy", "year": 2025},
        """Travel and Expense Policy 2025. Meals are reimbursed up to 35 dollars per day while travelling. Receipts are required for every expense above 25 dollars. Flights shorter than 6 hours must be booked in economy class, and hotels are capped at 180 dollars per night in standard cities. Expenses up to 500 dollars need approval from the direct manager, expenses between 500 and 2000 dollars need department head approval, and anything above 2000 dollars requires VP approval. Claims must be submitted in the Expensify tool within 30 days of the expense. Approved claims are reimbursed within 10 business days. Personal entertainment, alcohol and traffic fines are never reimbursable.""",
    ),
    "eng_incident_runbook_2024.txt": (
        {"department": "Engineering", "doc_type": "runbook", "year": 2024},
        """Incident Response Runbook 2024. Severity 1 incidents require acknowledgement within 5 minutes, and an incident commander must be assigned within 10 minutes. Severity 2 incidents require acknowledgement within 30 minutes. Error ERR-4021 means the payment gateway timed out; check the gateway circuit breaker and fail over to the secondary provider Payzen. Error ERR-5003 indicates database replica lag above 30 seconds; promote the standby replica only after confirming that the primary is unhealthy. Error ERR-7788 signals a cache eviction storm in Redis; scale the cache cluster and enable request coalescing. Status page updates are posted every 20 minutes during a Severity 1 incident. Every incident needs a blameless postmortem within 5 business days.""",
    ),
    "eng_deployment_guide_2025.txt": (
        {"department": "Engineering", "doc_type": "runbook", "year": 2025},
        """Deployment Guide 2025. Nimbus Labs uses blue-green deployments for all customer-facing services. Every release first goes to a canary that receives 5 percent of traffic for 30 minutes. If the error rate exceeds 1 percent during the canary phase, the pipeline rolls back automatically. A manual rollback is done with the command nimbusctl rollback --to previous. A code freeze applies every Friday after 3 PM local time and during the last week of each quarter. Every pull request needs two approvals, and at least one reviewer must belong to the owning team. Database migrations must stay backward compatible for at least one release. Feature flags live in the FlagHub console and should be removed within 60 days.""",
    ),
    "eng_architecture_overview_2024.txt": (
        {"department": "Engineering", "doc_type": "report", "year": 2024},
        """Platform Architecture Overview 2024. The platform consists of about 40 microservices running on Kubernetes in two regions, Mumbai and Frankfurt. All external traffic enters through the Atlas API gateway, which handles authentication and rate limiting. Services communicate asynchronously through a Kafka event bus with a seven day retention window. The main datastore is PostgreSQL with one primary and two read replicas per region. Redis is used as a cache for session data and hot catalog queries. Observability is based on Prometheus, Grafana and Loki. The service level objectives are 99.95 percent availability and a p99 latency below 300 milliseconds. Disaster recovery targets a recovery time of 1 hour and a recovery point of 5 minutes.""",
    ),
    "legal_data_privacy_policy_2025.txt": (
        {"department": "Legal", "doc_type": "policy", "year": 2025},
        """Data Privacy and Retention Policy 2025. Customer personal data is retained for 24 months after contract termination and then deleted. Data subject access requests must be answered within 30 days. All personal data is encrypted at rest with AES-256 and in transit with TLS 1.3. Security breaches affecting personal data must be reported to the regulator within 72 hours of discovery. Employees may only access customer data on a need-to-know basis, and every access is logged. Transfers of personal data outside the EU require standard contractual clauses. The Data Protection Officer can be reached at dpo@nimbuslabs.example. Marketing emails require explicit opt-in consent, which can be withdrawn at any time.""",
    ),
    "support_faq_2025.txt": (
        {"department": "Support", "doc_type": "faq", "year": 2025},
        """Customer Support FAQ 2025. To reset a password, click Forgot Password on the login page; the reset link expires after 30 minutes. Premium customers receive a first response within 1 hour, while Standard customers receive a first response within 8 business hours. Refunds are available within 14 days of purchase for annual plans, and the money is returned to the original payment method. Data can be exported as CSV or JSON from Settings and then Data Export; large exports are emailed within 24 hours. Single sign-on is supported through SAML 2.0 and is available on Business and Enterprise plans. Accounts are locked after 5 failed login attempts. Premium customers can call the 24x7 support hotline outside business hours.""",
    ),
}


def main():
    out = Path("data")
    out.mkdir(exist_ok=True)
    meta = {}
    for fname, (m, text) in DOCS.items():
        (out / fname).write_text(text.strip() + "\n", encoding="utf-8")
        meta[fname] = m
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {len(DOCS)} documents to {out.resolve()}")


if __name__ == "__main__":
    main()
