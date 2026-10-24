"""Tests instantiate the actual CrewAI BaseTool: no credentials or payments."""
import base64
import json
import unittest
from unittest.mock import MagicMock

import requests
from crewai.tools import BaseTool

from biq_crewai import BlockchainIQMarketBriefTool
from biq_crewai.preflight import (
    AMOUNT_ATOMIC_USDC, BRIEF_URL, CHAIN, SPONSOR_RECEIVER,
    USDC_CONTRACT, ChallengeError, validate_payment_challenge,
    validate_settlement_receipt
)


def b64json(o):
    return base64.b64encode(json.dumps(o).encode()).decode()


def valid_challenge():
    return b64json({"x402Version": 2, "resource":{"url": BRIEF_URL},
        "accepts":[{"scheme":"exact","network":CHAIN,"asset":USDC_CONTRACT,
                    "amount":AMOUNT_ATOMIC_USDC,"payTo":SPONSOR_RECEIVER}]})


def response(status=200, body=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = (json.dumps({"data":{"btc":100}}) if body is None else body).encode()
    r.headers.update(headers or {})
    return r


class CrewAIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.http = MagicMock()
        self.http.get.return_value = response()
        self.tool = BlockchainIQMarketBriefTool(http_session=self.http)

    def test_real_framework_subclass(self):
        self.assertIsInstance(self.tool, BaseTool)
        self.assertIn("BlockchainIQ", self.tool.name)
        self.assertEqual(self.tool.args_schema.model_fields, {})
        self.assertIsInstance(self.tool.run({}), str)

    def test_request_pinned_and_no_payment_by_default(self):
        value = json.loads(self.tool._run())
        self.assertEqual(value["payload"]["data"]["btc"], 100)
        self.assertFalse(value["paidReceiptVerified"])
        args, kwargs = self.http.get.call_args
        self.assertEqual(args[0], BRIEF_URL)
        self.assertFalse(kwargs["allow_redirects"])

    def test_unpaid_402_explicitly_errors(self):
        self.http.get.return_value = response(402)
        with self.assertRaisesRegex(ValueError, "PAYMENT_REQUIRED"):
            self.tool._run()

    def test_not_found_explicitly_errors(self):
        self.http.get.return_value = response(404)
        with self.assertRaisesRegex(ValueError, "HTTP 404"):
            self.tool._run()

    def test_malformed_json_explicitly_errors(self):
        self.http.get.return_value = response(200, "{bad")
        with self.assertRaisesRegex(ValueError, "Malformed JSON"):
            self.tool._run()

    def test_oversized_json_rejected(self):
        self.http.get.return_value = response(200, "x" * 270000)
        with self.assertRaisesRegex(ValueError, "Oversized"):
            self.tool._run()

    def test_challenge_exact_true(self):
        self.assertEqual(validate_payment_challenge(valid_challenge())["expectedUSD"], "0.01")

    def test_changed_merchant_rejected(self):
        x = json.loads(base64.b64decode(valid_challenge()))
        x["accepts"][0]["payTo"] = "0x" + "f" * 40
        with self.assertRaises(ChallengeError):
            validate_payment_challenge(b64json(x))

    def test_extra_payment_option_rejected(self):
        x = json.loads(base64.b64decode(valid_challenge()))
        x["accepts"].append(x["accepts"][0])
        with self.assertRaises(ChallengeError):
            validate_payment_challenge(b64json(x))

    def test_changed_price_rejected(self):
        x = json.loads(base64.b64decode(valid_challenge()))
        x["accepts"][0]["amount"] = "20000"
        with self.assertRaises(ChallengeError):
            validate_payment_challenge(b64json(x))

    def test_invalid_receipt_rejected(self):
        with self.assertRaises(ChallengeError):
            validate_settlement_receipt(b64json({"success":False,"network":CHAIN,"transaction":"0x" + "a"*64}))

    def test_valid_mock_receipt_parser_but_not_real_settlement(self):
        encoded=b64json({"success":True,"network":CHAIN,"transaction":"0x" + "a"*64})
        self.assertTrue(validate_settlement_receipt(encoded)["settled"])

    def test_actual_sdk_quote_policy_enforces_payment_receiver(self):
        from types import SimpleNamespace
        from biq_crewai.payer import _only_exact_sponsor_quote
        def quote(merchant=SPONSOR_RECEIVER, amount=AMOUNT_ATOMIC_USDC):
            return SimpleNamespace(
                scheme="exact", network=CHAIN, asset=USDC_CONTRACT,
                pay_to=merchant, get_amount=lambda: amount,
            )
        self.assertEqual(len(_only_exact_sponsor_quote(2, [quote()])), 1)
        self.assertEqual(_only_exact_sponsor_quote(2, [quote(merchant="0x" + "0"*40)]), [])
        self.assertEqual(_only_exact_sponsor_quote(2, [quote(amount="20000")]), [])
        self.assertEqual(_only_exact_sponsor_quote(1, [quote()]), [])

    def test_explicit_settlement_mode_refuses_missing_header(self):
        t=BlockchainIQMarketBriefTool(http_session=self.http,require_settlement=True)
        with self.assertRaises(ChallengeError):
            t._run()


if __name__ == "__main__":
    unittest.main()
