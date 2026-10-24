"""Runs a genuine CrewAI tool (without starting a language model).

No API key or LLM credit is needed for proof of framework tool integration.
"""
import json
import sys

import requests

from .preflight import BRIEF_URL, SAMPLE_URL, validate_payment_challenge
from .tool import BlockchainIQMarketBriefTool


def main():
    mode = sys.argv[1:] if len(sys.argv) > 1 else ["--probe"]
    if mode == ["--sample"]:
        r = requests.get(SAMPLE_URL, timeout=15, allow_redirects=False)
        r.raise_for_status()
        assert isinstance(r.json(), dict)
        print(json.dumps({"mode": "sample", "http": r.status_code, "paid": False}))
    elif mode == ["--probe"]:
        r = requests.get(BRIEF_URL, headers={"Accept": "application/json"},
                         timeout=15, allow_redirects=False)
        if r.status_code != 402:
            raise ValueError("Expected unpaid x402 HTTP 402")
        detail = validate_payment_challenge(r.headers.get("PAYMENT-REQUIRED"))
        print(json.dumps({"mode": "read-only-probe", "http": r.status_code,
                          "quoteValidated": True, "paid": False, **detail}))
    elif mode == ["--paid"]:
        from .payer import build_one_call_paid_session
        session = build_one_call_paid_session()
        tool = BlockchainIQMarketBriefTool(http_session=session, require_settlement=True)
        result = json.loads(tool._run())
        receipt = result.get("settlement")
        if not receipt or not receipt.get("settled"):
            raise ValueError("Missing real confirmed paid receipt")
        print(json.dumps({"framework": "CrewAI", "tool": tool.name,
                          "paidReceiptVerified": True, **receipt}))
    else:
        raise SystemExit("Usage: python -m biq_crewai.demo --sample|--probe|--paid")


if __name__ == "__main__":
    main()
