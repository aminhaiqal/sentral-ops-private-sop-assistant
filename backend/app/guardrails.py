from __future__ import annotations

import re

from app.schemas import BoundaryWarning


BOUNDARY_MESSAGES = {
    "live_delivery_status": (
        "This asks for live delivery status or ETA. The assistant can explain the SOP, "
        "but staff must check the order system or Operations for current status."
    ),
    "payment_confirmation": (
        "This asks for payment confirmation. The assistant cannot verify bank receipts, "
        "customer ledger status, or final payment clearance."
    ),
    "stock_availability": (
        "This asks for current stock availability. The assistant can explain exception rules, "
        "but stock must be checked in the approved inventory or purchasing channel."
    ),
    "approval_authority": (
        "This may require manager approval or final decision authority. The assistant can cite the "
        "approval matrix, but it cannot approve the action."
    ),
    "confidential_data": (
        "This may involve customer, invoice, payment, or personal data. Staff should avoid sharing "
        "confidential data outside approved internal systems."
    ),
    "external_ai": (
        "This involves public AI tools. The assistant can explain the policy, but confidential company "
        "or customer data must not be pasted into external AI services."
    ),
    "substitution_approval": (
        "This asks about product substitution. The assistant can explain the SOP, but customer approval "
        "or manager approval may be required before action is taken."
    ),
}


RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "live_delivery_status",
        re.compile(r"\b(today|now|current|live|eta|arrival|arrive|delivery status|where is)\b", re.I),
    ),
    (
        "payment_confirmation",
        re.compile(r"\b(payment confirmed|paid|payment status|receipt|bank in|clear(ed)?|ledger)\b", re.I),
    ),
    (
        "stock_availability",
        re.compile(r"\b(stock|availability|available|inventory|on hand|out of stock)\b", re.I),
    ),
    (
        "approval_authority",
        re.compile(
            r"\b(can i approve|can we approve|am i allowed to approve|may i approve|approve a|"
            r"approve an|approval authority|final decision|authori[sz]e|rm\s?\d)",
            re.I,
        ),
    ),
    (
        "confidential_data",
        re.compile(
            r"\b(customer\s+(?:[a-z]{2,5}|\d{2,})\b|invoice data|invoice|personal data|nric|bank account|"
            r"confidential|customer data)\b",
            re.I,
        ),
    ),
    ("external_ai", re.compile(r"\b(chatgpt|public ai|external ai|gemini|claude)\b", re.I)),
    (
        "substitution_approval",
        re.compile(r"\b(substitute|substitution|replace item|alternative item|without customer approval)\b", re.I),
    ),
]


def evaluate_question(question: str) -> list[BoundaryWarning]:
    warnings: list[BoundaryWarning] = []
    seen: set[str] = set()

    for category, pattern in RULES:
        if category in seen:
            continue
        if pattern.search(question):
            seen.add(category)
            warnings.append(BoundaryWarning(category=category, message=BOUNDARY_MESSAGES[category]))

    return warnings


def boundary_prompt(warnings: list[BoundaryWarning]) -> str:
    if not warnings:
        return "No special boundary warning was detected."

    lines = ["Boundary warnings detected:"]
    for warning in warnings:
        lines.append(f"- {warning.category}: {warning.message}")
    return "\n".join(lines)
