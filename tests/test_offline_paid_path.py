"""No-network paid-path tests for genuine CrewAI BaseTool and official x402.

All keys and transactions below are obviously synthetic, never funded,
and not a receipt or basis for any real bounty claim.
"""
import base64
import json
import os
import unittest
from unittest.mock import patch

import requests
from requests.adapters import HTTPAdapter
from biq_crewai.payer import build_one_call_paid_session
from biq_crewai.preflight import BRIEF_URL, CHAIN, USDC_CONTRACT, SPONSOR_RECEIVER, AMOUNT_ATOMIC_USDC
from biq_crewai.tool import BlockchainIQMarketBriefTool

DUMMY_TEST_ONLY_SIGNER_KEY = "0x" + "3" * 64
FAKE_NOT_ON_CHAIN_HASH = "0x" + "a" * 64


def encoded(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


def offer(recipient=SPONSOR_RECEIVER, amount=AMOUNT_ATOMIC_USDC):
    return {"x402Version": 2,
            "resource": {"url": BRIEF_URL, "mimeType": "application/json"},
            "accepts": [{
                "scheme": "exact", "network": CHAIN, "asset": USDC_CONTRACT,
                "payTo": recipient, "amount": amount, "maxTimeoutSeconds": 300,
                "extra": {"name": "USD Coin", "version": "2"},
            }]}


def response(request, status, body, headers):
    out = requests.Response()
    out.status_code = status
    out._content = json.dumps(body).encode()
    out.headers.update(headers)
    out.url = request.url if request else BRIEF_URL
    out.request = request
    return out


class FullOfficialSDKOfflineTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch.dict(os.environ, {
            "BIQ_CREWAI_CONFIRM_SPEND_ONE_CENT": "YES",
            "BIQ_CREWAI_DISPOSABLE_TEST_PRIVATE_KEY": DUMMY_TEST_ONLY_SIGNER_KEY,
        })
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.observed = []
        self.first = response(None, 402, {"error": "402"},
                              {"PAYMENT-REQUIRED": encoded(offer())})

    def run_synthetic_flow(self, subsequent_offer):
        calls = self.observed
        receipt = encoded({"success": True, "network": CHAIN,
                           "transaction": FAKE_NOT_ON_CHAIN_HASH})

        def offline_send(_adapter, request, **_kwargs):
            self.assertEqual(request.url, BRIEF_URL)
            self.assertEqual(request.method, "GET")
            signature = request.headers.get("PAYMENT-SIGNATURE")
            calls.append(signature)
            if signature:
                return response(request, 200, {"data": {"synthetic": True}},
                                {"PAYMENT-RESPONSE": receipt})
            return response(request, 402, {"error": "synthetic quote"},
                            {"PAYMENT-REQUIRED": encoded(subsequent_offer)})

        # Intercept preflight and all adapter traffic, no outbound network.
        with patch("biq_crewai.payer.requests.get", return_value=self.first) as probe, \
             patch.object(HTTPAdapter, "send", new=offline_send):
            session = build_one_call_paid_session()
            tool = BlockchainIQMarketBriefTool(
                http_session=session, require_settlement=True)
            try:
                outcome = json.loads(tool._run())
            except Exception as exc:
                outcome = exc
            self.assertEqual(probe.call_count, 1)
            return outcome

    def test_one_cent_official_sdk_signature_mock_only(self):
        result = self.run_synthetic_flow(offer())
        self.assertIsInstance(result, dict, repr(result))
        self.assertEqual(len(self.observed), 2)
        self.assertIsNone(self.observed[0])
        self.assertIsNotNone(self.observed[1])
        signed = json.loads(base64.b64decode(self.observed[1]))
        self.assertEqual(signed["x402Version"], 2)
        self.assertEqual(signed["accepted"]["network"], CHAIN)
        self.assertEqual(signed["accepted"]["asset"].lower(),
                         USDC_CONTRACT.lower())
        self.assertEqual(signed["accepted"]["payTo"].lower(),
                         SPONSOR_RECEIVER.lower())
        self.assertEqual(str(signed["accepted"]["amount"]), AMOUNT_ATOMIC_USDC)
        self.assertEqual(signed["payload"]["authorization"]["to"].lower(),
                         SPONSOR_RECEIVER.lower())
        self.assertEqual(str(signed["payload"]["authorization"]["value"]),
                         AMOUNT_ATOMIC_USDC)
        self.assertEqual(result["settlement"]["transactionHash"],
                         FAKE_NOT_ON_CHAIN_HASH)
        self.assertTrue(result["payload"]["data"]["synthetic"])
        self.assertTrue(result["settlementHeaderValidated"])
        self.assertFalse(result["independentOnchainVerified"])

    def test_malicious_recipient_switch_never_signed(self):
        result = self.run_synthetic_flow(
            offer(recipient="0x" + "9" * 40))
        self.assertIsInstance(result, Exception)
        self.assertEqual(self.observed, [None])

    def test_malicious_price_increase_never_signed(self):
        result = self.run_synthetic_flow(offer(amount="20000"))
        self.assertIsInstance(result, Exception)
        self.assertEqual(self.observed, [None])

    def test_user_confirmation_missing_blocks_before_io(self):
        with patch.dict(os.environ, {"BIQ_CREWAI_CONFIRM_SPEND_ONE_CENT": ""}), \
             patch("biq_crewai.payer.requests.get",
                   side_effect=AssertionError("unexpected network request")):
            with self.assertRaises(PermissionError):
                build_one_call_paid_session()


if __name__ == "__main__":
    unittest.main()
