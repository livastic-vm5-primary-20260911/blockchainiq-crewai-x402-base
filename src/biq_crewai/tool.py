"""Real CrewAI BaseTool with default NO-SPEND HTTP session.

To pay, an operator injects the official Python x402 requests Session,
which handles the signed retry of an HTTP 402 challenge. No key can enter
tool inputs, crew memory or a repository file.
"""
import json
from typing import Any, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, PrivateAttr

from .preflight import BRIEF_URL, MAX_RESULT_BYTES, validate_settlement_receipt


class BriefArguments(BaseModel):
    """One parameter-free market-brief request; no arbitrary URL input."""
    model_config = ConfigDict(extra="forbid")


class BlockchainIQMarketBriefTool(BaseTool):
    name: str = "BlockchainIQ_Crypto_Market_Brief"
    description: str = (
        "Return a current Blockchain IQ market brief for BTC/ETH/SOL/XRP and 48-hour event risk. "
        "A real request costs 0.01 Circle USDC on Base if an explicitly paid x402 session "
        "is injected. Default is NO PAYMENT. Research data, not trading advice."
    )
    args_schema: Type[BaseModel] = BriefArguments

    _http: Any = PrivateAttr(default=None)
    _need_real_settlement: bool = PrivateAttr(default=False)

    def __init__(self, http_session=None, require_settlement=False, **kwargs):
        super().__init__(**kwargs)
        self._http = http_session if http_session is not None else requests.Session()
        self._need_real_settlement = bool(require_settlement)

    def _run(self, params=None, **kwargs) -> str:
        if params not in (None, {}) or kwargs:
            raise ValueError("This brief tool takes no user-supplied arguments")
        response = self._http.get(
            BRIEF_URL, headers={"Accept": "application/json"},
            timeout=20, allow_redirects=False,
        )
        if response.status_code == 402:
            raise ValueError("PAYMENT_REQUIRED: read-only mode did not spend USDC")
        if response.status_code != 200:
            raise ValueError("Blockchain IQ returned HTTP " + str(response.status_code))
        if len(response.content) > MAX_RESULT_BYTES:
            raise ValueError("Oversized Blockchain IQ JSON refused")
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed JSON response") from exc
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object from Blockchain IQ")

        receipt_header = response.headers.get("PAYMENT-RESPONSE")
        # In paid mode we never count a 200/synthetic mock as a paid success.
        receipt = validate_settlement_receipt(receipt_header) if self._need_real_settlement else None
        result = {"source": "Blockchain IQ", "resource": "brief",
                  "paidReceiptVerified": receipt is not None, "payload": data}
        if receipt is not None:
            result["settlement"] = receipt
        return json.dumps(result, ensure_ascii=False)
