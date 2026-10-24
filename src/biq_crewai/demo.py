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
    elif len(mode) == 3 and mode[0] == "--verify-tx":
        # Read-only independent confirmation, NO signer required; safe to retry.
        from .onchain import verify_base_usdc_payment
        proof = verify_base_usdc_payment(mode[1], mode[2])
        print(json.dumps(proof))
    elif mode == ["--paid"]:
        # One original paid call only, explicitly confirmed. Do not retry the paid
        # mode when the RPC is unavailable; re-run --verify-tx instead.
        import os
        from eth_account import Account
        from .onchain import verify_base_usdc_payment, ChainProofError

        from .payer import build_one_call_paid_session
        session = build_one_call_paid_session()
        # Public address, derived in memory from the optional disposable signer.
        payer = Account.from_key(os.environ["BIQ_CREWAI_DISPOSABLE_TEST_PRIVATE_KEY"]).address
        tool = BlockchainIQMarketBriefTool(http_session=session, require_settlement=True)
        result = json.loads(tool._run())
        receipt = result.get("settlement")
        if not result.get("settlementHeaderValidated") or not receipt:
            raise ValueError("No syntactically valid PAYMENT-RESPONSE. Do not claim a purchase.")
        # Always surface the claimed public hash FIRST. Network/RPC outages
        # cannot cause a later second paid call to the resource.
        print(json.dumps({
            "framework": "CrewAI", "tool": tool.name,
            "issuerClaimsPaid": True, "independentOnchainVerified": False,
            "claimedTransactionHash": receipt["transactionHash"],
            "payerAddress": payer,
            "nextSafeAction": "read-only --verify-tx; do NOT rerun --paid"
        }))
        try:
            proof = verify_base_usdc_payment(receipt["transactionHash"], payer)
        except (ChainProofError, requests.RequestException, ValueError) as exc:
            print(json.dumps({
                "independentOnchainVerified": False,
                "reason": str(exc)[:200],
                "nextSafeAction": "python -m biq_crewai.demo --verify-tx TRANSACTION_HASH PUBLIC_PAYER_ADDRESS"
            }))
        else:
            print(json.dumps(proof))
    else:
        raise SystemExit("Usage: python -m biq_crewai.demo --sample|--probe|--paid or --verify-tx HASH PAYER_ADDRESS")


if __name__ == "__main__":
    main()
