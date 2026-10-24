"""Read-only exact payment challenge and settlement checks.

This module cannot sign any transaction and does not hold a payment key.
"""
import base64
import binascii
import json
import re

BRIEF_URL = "https://www.blockchainiq.co/api/x402/v1/brief"
SAMPLE_URL = "https://www.blockchainiq.co/api/x402/v1/sample"
CHAIN = "eip155:8453"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
SPONSOR_RECEIVER = "0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e"
AMOUNT_ATOMIC_USDC = "10000"  # $0.01 with native Circle USDC's 6 decimals
MAX_RESULT_BYTES = 256000

class ChallengeError(ValueError):
    """A changed, malformed or over-budget quote cannot be purchased."""

def _decode_b64_json(value):
    if not isinstance(value, str) or not (10 <= len(value) <= 16384):
        raise ChallengeError("Missing or oversized encoded x402 payload")
    try:
        return json.loads(base64.b64decode(value, validate=True))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ChallengeError("Invalid x402 JSON base64") from exc

def validate_payment_challenge(header):
    """Reject every other network, payee, token, route or price before signing."""
    challenge = _decode_b64_json(header)
    if not isinstance(challenge, dict) or challenge.get("x402Version") != 2:
        raise ChallengeError("Not x402 v2")
    resource = challenge.get("resource")
    if not isinstance(resource, dict) or resource.get("url") != BRIEF_URL:
        raise ChallengeError("Unexpected resource URL")
    accepts = challenge.get("accepts")
    if not isinstance(accepts, list) or len(accepts) != 1 or not isinstance(accepts[0], dict):
        raise ChallengeError("Unexpected number of payment options")
    quote = accepts[0]
    if (quote.get("scheme") != "exact"
        or quote.get("network") != CHAIN
        or str(quote.get("asset", "")).lower() != USDC_CONTRACT.lower()
        or str(quote.get("payTo", "")).lower() != SPONSOR_RECEIVER.lower()
        or str(quote.get("amount")) != AMOUNT_ATOMIC_USDC):
        raise ChallengeError("The network/token/recipient/amount differs from the approved 0.01 USDC quote")
    return {
        "route": BRIEF_URL, "network": CHAIN, "asset": USDC_CONTRACT,
        "recipient": SPONSOR_RECEIVER, "amountAtomic": AMOUNT_ATOMIC_USDC,
        "expectedUSD": "0.01",
    }

def validate_settlement_receipt(value):
    receipt = _decode_b64_json(value)
    if not isinstance(receipt, dict):
        raise ChallengeError("Missing settlement response object")
    if receipt.get("success") is not True or receipt.get("network") != CHAIN:
        raise ChallengeError("Settlement unsuccessful or wrong network")
    tx = receipt.get("transaction")
    if not isinstance(tx, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx):
        raise ChallengeError("Missing valid on-chain transaction hash")
    return {"transactionHash": tx, "network": CHAIN, "settled": True}
