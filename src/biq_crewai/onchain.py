"""Independent read-only validation of an issuer-supplied Base USDC settlement.

The merchant's PAYMENT-RESPONSE header is an untrusted claim: a syntactically
correct transaction hash is not proof that Circle USDC was actually paid.
No key, signer, approval, broadcast or wallet permissions enter this module.
"""
import re
import requests

from .preflight import CHAIN, USDC_CONTRACT, SPONSOR_RECEIVER, AMOUNT_ATOMIC_USDC

BASE_RPC = "https://base-rpc.publicnode.com"
BASE_CHAIN_ID = 8453
# Event: Transfer(address indexed from, address indexed to, uint256 value)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
HASH = re.compile(r"0x[0-9a-fA-F]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


class ChainProofError(ValueError):
    """An RPC response does not prove the exact recipient-token-payer transfer."""


def _quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise ChainProofError("Invalid canonical EVM quantity")
    return int(value, 16)


def _read_rpc(method, params, post, url):
    if url != BASE_RPC:
        raise ChainProofError("Refusing non-pinned RPC URL")
    response = post(url, json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }, timeout=12)
    response.raise_for_status()
    if len(response.content) > 256_000:
        raise ChainProofError("Oversize RPC response")
    message = response.json()
    if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
            or message.get("id") != 1 or "error" in message
            or "result" not in message):
        raise ChainProofError("Invalid RPC result")
    return message["result"]


def verify_base_usdc_payment(tx_hash, payer_address, *, min_confirmations=2,
                             post=requests.post, rpc_url=BASE_RPC):
    """Match one real native Circle USDC Transfer event in a successful Base receipt.

    Use only after a genuine signed x402 purchase and its externally supplied
    transaction hash. Return a public, independently validated proof or raise.
    This function never signs, never moves funds, and cannot prove sponsor award.
    """
    if not isinstance(tx_hash, str) or not HASH.fullmatch(tx_hash):
        raise ChainProofError("Invalid transaction hash")
    if not isinstance(payer_address, str) or not ADDRESS.fullmatch(payer_address):
        raise ChainProofError("Invalid public payer address")
    if not isinstance(min_confirmations, int) or not 1 <= min_confirmations <= 500:
        raise ChainProofError("Invalid required confirmation depth")

    network = _quantity(_read_rpc("eth_chainId", [], post, rpc_url))
    if network != BASE_CHAIN_ID:
        raise ChainProofError("Expected Base mainnet chainId 8453")
    receipt = _read_rpc("eth_getTransactionReceipt", [tx_hash], post, rpc_url)
    if not isinstance(receipt, dict):
        raise ChainProofError("No mined transaction receipt yet")
    if receipt.get("transactionHash", "").lower() != tx_hash.lower():
        raise ChainProofError("Returned receipt is not requested transaction")
    if _quantity(receipt.get("status")) != 1:
        raise ChainProofError("Transaction did not succeed")
    block = _quantity(receipt.get("blockNumber"))
    latest = _quantity(_read_rpc("eth_blockNumber", [], post, rpc_url))
    depth = latest - block + 1
    if depth < min_confirmations:
        raise ChainProofError("Insufficient block confirmations")
    logs = receipt.get("logs")
    if not isinstance(logs, list) or len(logs) > 10_000:
        raise ChainProofError("Invalid or excessive event logs")

    matches = []
    for log in logs:
        if not isinstance(log, dict) or log.get("removed") is True:
            continue
        if str(log.get("address", "")).lower() != USDC_CONTRACT.lower():
            continue
        if log.get("transactionHash", "").lower() != tx_hash.lower():
            continue
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) != 3:
            continue
        if not all(isinstance(t, str) and HASH.fullmatch(t) for t in topics):
            continue
        if topics[0].lower() != TRANSFER_TOPIC:
            continue
        # An indexed Ethereum address occupies the last 20 bytes of 32.
        if (topics[1][2:26] != "0"*24 or topics[2][2:26] != "0"*24):
            continue
        frm = "0x"+topics[1][-40:]
        to = "0x"+topics[2][-40:]
        if frm.lower() != payer_address.lower() or to.lower() != SPONSOR_RECEIVER.lower():
            continue
        value = log.get("data")
        if not isinstance(value, str) or not HASH.fullmatch(value):
            continue
        if int(value, 16) != int(AMOUNT_ATOMIC_USDC):
            continue
        matches.append(log)

    if len(matches) != 1:
        raise ChainProofError("No UNIQUE exact 0.01 Base Circle USDC transfer payer-to-sponsor in receipt")
    index = _quantity(matches[0].get("logIndex"))
    return {
        "independentOnchainVerified": True,
        "transactionHash": tx_hash,
        "logIndex": index,
        "blockNumber": block,
        "confirmations": depth,
        "network": CHAIN,
        "token": USDC_CONTRACT,
        "payerAddress": payer_address,
        "merchantAddress": SPONSOR_RECEIVER,
        "amountUSDC": "0.010000",
        "rpcProvider": BASE_RPC,
    }
