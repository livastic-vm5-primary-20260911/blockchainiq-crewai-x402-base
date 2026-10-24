"""One optionally authorized purchase using the official x402 Python v2 SDK.

Never pass a main wallet secret. This exact-quote preflight detects changed
payment terms before the SDK can create a signed EIP-3009 authorization.
"""
import os
import re

import requests
from eth_account import Account
from x402 import SchemeRegistration, x402ClientConfig, x402ClientSync
from x402.http.clients.requests import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmScheme

from .preflight import (BRIEF_URL, CHAIN, USDC_CONTRACT, SPONSOR_RECEIVER,
                        AMOUNT_ATOMIC_USDC, validate_payment_challenge)



def _only_exact_sponsor_quote(version, requirements):
    # This SDK policy filters the actual 402 offer seen DURING the signed retry.
    # A changed recipient/price/asset is denied even after the earlier preflight.
    if version != 2:
        return []
    return [
        r for r in requirements
        if r.scheme == "exact"
        and r.network == CHAIN
        and str(r.asset).lower() == USDC_CONTRACT.lower()
        and str(r.pay_to).lower() == SPONSOR_RECEIVER.lower()
        and str(r.get_amount()) == AMOUNT_ATOMIC_USDC
    ]

def build_one_call_paid_session():
    if os.environ.get("BIQ_CREWAI_CONFIRM_SPEND_ONE_CENT") != "YES":
        raise PermissionError("Paid operation not authorized for this invocation")
    private_key = os.environ.get("BIQ_CREWAI_DISPOSABLE_TEST_PRIVATE_KEY", "")
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", private_key):
        raise ValueError("A dedicated, low-balance test signer must be supplied privately")

    # Validate the issuer's published payment challenge before constructing a signer.
    probe = requests.get(BRIEF_URL, headers={"Accept": "application/json"},
                         timeout=12, allow_redirects=False)
    if probe.status_code != 402:
        raise ValueError("Expected HTTP 402 challenge; refusing purchase")
    validate_payment_challenge(probe.headers.get("PAYMENT-REQUIRED"))

    signer = EthAccountSigner(Account.from_key(private_key))
    config = x402ClientConfig(
        schemes=[SchemeRegistration(network=CHAIN, client=ExactEvmScheme(signer))],
        spend_controls={"max_amount_per_payment": "$0.01"},
        policies=[_only_exact_sponsor_quote],
    )
    payment_client = x402ClientSync.from_config(config)
    return x402_requests(payment_client)
