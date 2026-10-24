"""Read-only chain receipt verification, entirely offline mocked JSON-RPC."""
import json
import unittest
from unittest.mock import Mock

from biq_crewai.onchain import (
    verify_base_usdc_payment, ChainProofError, BASE_RPC, TRANSFER_TOPIC,
)
from biq_crewai.preflight import USDC_CONTRACT, SPONSOR_RECEIVER

TX = "0x"+"d"*64
PAYER = "0x"+"a"*40


def topic(address):
    return "0x"+("0"*24)+address.lower()[2:]


def log(**changes):
    obj = {"address": USDC_CONTRACT, "transactionHash": TX,
           "topics": [TRANSFER_TOPIC, topic(PAYER), topic(SPONSOR_RECEIVER)],
           "data": "0x"+format(10000, "064x"), "logIndex": "0x5",
           "removed": False}
    obj.update(changes)
    return obj


def receipt(logs=None, status="0x1", block="0x64"):
    return {"transactionHash": TX, "status": status,
            "blockNumber": block, "logs": [log()] if logs is None else logs}


def fake_rpc(r, *, latest="0x70", chain="0x2105"):
    observed = []
    def post(url, *, json, timeout):
        assert url == BASE_RPC
        method = json["method"]
        observed.append(method)
        results = {"eth_chainId": chain, "eth_getTransactionReceipt": r,
                   "eth_blockNumber": latest}
        return Mock(status_code=200, content=b"{}",
                    json=lambda: {"jsonrpc": "2.0", "id": 1, "result": results[method]},
                    raise_for_status=lambda: None)
    return post, observed


class ReceiptProofTests(unittest.TestCase):
    def test_exact_real_shape_but_all_fake_data_valid(self):
        post, methods = fake_rpc(receipt())
        proven = verify_base_usdc_payment(TX, PAYER, post=post)
        self.assertTrue(proven["independentOnchainVerified"])
        self.assertEqual(proven["logIndex"], 5)
        self.assertEqual(proven["amountUSDC"], "0.010000")
        self.assertEqual(methods, ["eth_chainId", "eth_getTransactionReceipt", "eth_blockNumber"])

    def test_wrong_chain_fails_before_receipt(self):
        post, seen = fake_rpc(receipt(), chain="0x1")
        with self.assertRaisesRegex(ChainProofError, "chainId"):
            verify_base_usdc_payment(TX, PAYER, post=post)
        self.assertEqual(seen, ["eth_chainId"])

    def test_wrong_token_fails(self):
        post, _ = fake_rpc(receipt([log(address="0x"+"1"*40)]))
        with self.assertRaisesRegex(ChainProofError, "UNIQUE"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_wrong_recipient_fails(self):
        post, _ = fake_rpc(receipt([log(topics=[
            TRANSFER_TOPIC, topic(PAYER), topic("0x"+"f"*40)])]))
        with self.assertRaisesRegex(ChainProofError, "UNIQUE"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_wrong_payer_fails(self):
        post, _ = fake_rpc(receipt([log(topics=[
            TRANSFER_TOPIC, topic("0x"+"1"*40), topic(SPONSOR_RECEIVER)])]))
        with self.assertRaisesRegex(ChainProofError, "UNIQUE"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_wrong_amount_fails(self):
        post, _ = fake_rpc(receipt([log(data="0x"+format(20000,"064x"))]))
        with self.assertRaisesRegex(ChainProofError, "UNIQUE"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_reverted_tx_fails(self):
        post, _ = fake_rpc(receipt(status="0x0"))
        with self.assertRaisesRegex(ChainProofError, "succeed"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_tx_pending_fails(self):
        post, _ = fake_rpc(None)
        with self.assertRaisesRegex(ChainProofError, "mined"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_not_confirmed_fails(self):
        post, _ = fake_rpc(receipt(block="0x70"), latest="0x70")
        with self.assertRaisesRegex(ChainProofError, "confirmations"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_duplicate_matching_logs_fails(self):
        post, _ = fake_rpc(receipt([log(),log(logIndex="0x6")]))
        with self.assertRaisesRegex(ChainProofError, "UNIQUE"):
            verify_base_usdc_payment(TX, PAYER, post=post)

    def test_no_external_calls_for_invalid_tx(self):
        post, calls = fake_rpc(receipt())
        with self.assertRaisesRegex(ChainProofError, "transaction hash"):
            verify_base_usdc_payment("not-a-hash", PAYER, post=post)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
