# Blockchain IQ x402 + CrewAI — independently authored BaseTool

A purpose-built **CrewAI Python BaseTool** for the [Blockchain IQ agent-framework builder bounty](https://www.blockchainiq.co/blog/x402-build-bounties), using the official **x402 Python v2** SDK. Supports the sponsor's USD 0.01 market brief at https://www.blockchainiq.co/api/x402/v1/brief.

This is specifically the **CrewAI** slot, independent of the same original operator's separate **LangChain** submission, and not a second application to that LangChain slot. Both repositories are controlled by **one human beneficial owner**. This repo is not affiliated with Blockchain IQ, and no bounty, sponsorship or award has yet been earned.

## What is real

- `BlockchainIQMarketBriefTool` subclasses actual `crewai.tools.BaseTool`, defines a parameter-free Pydantic input schema and implements `_run` for the real sponsor API.
- In the **default** mode, `requests.Session` returns HTTP 402 and fails closed. No wallet or money is involved.
- In the optional **paid** path, a separately injected official `x402ClientSync` with `x402_requests` pays in Circle USDC on Base mainnet via x402 v2. Test keys exist only as environment variables; never put a key in this project.
- An **unpaid fresh GET probe** pins the entire challenge: HTTPS host/path, x402 v2, EVM network `eip155:8453`, official native Base Circle USDC contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, specific sponsor receiving address `0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e`, exact payment amount `10000` in 6-decimal units (0.01 USDC).
- An additional **payment policy inside the official x402 SDK** checks the actual 402 quote again before signing, so a changed merchant, chain, price or asset is rejected.
- The SDK `spend_controls` cap is USD 0.01 **per one purchase**. There is no automated repeat loop, trading or withdrawal.
- A paid response must carry a valid `PAYMENT-RESPONSE` header with a successful Base transaction hash. A synthetic/mock header or HTTP 200 is never evidence of a real bounty claim.

## Install and run

Python 3.11+:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m biq_crewai.demo --sample   # real free API; no USDC
python -m biq_crewai.demo --probe    # real x402 v2 challenge; no USDC
```

The tool can be passed to a CrewAI Agent using the normal `tools=[BlockchainIQMarketBriefTool(...)]` argument. No LLM API key or model inference is needed to run the standalone `demo` and tests.

The optional one-call payment requires a **dedicated disposable test signer with at most the cost you intend to spend**. It must be configured privately using `BIQ_CREWAI_DISPOSABLE_TEST_PRIVATE_KEY`, and the spend requires `BIQ_CREWAI_CONFIRM_SPEND_ONE_CENT=YES` and an explicit `--paid` mode:

```sh
# Only after privately injecting a disposable signer and explicitly authorizing a real purchase:
python -m biq_crewai.demo --paid
```

DO NOT paste any actual key into a terminal command, commit, mail, screenshot, environment example or issue. DO NOT use an owner main wallet. The provided sample deliberately contains no key material, auto-topup, unlimited ERC20 approvals or transfer functionality.

## Evidence / truthful status as of 2026-10-24

| Metric | Verified |
|---|---|
| Real CrewAI subclass and SDK installed | Yes, CrewAI 1.15.30, x402 2.25.0 |
| Deterministic tests, using CrewAI framework + SDK | 14 passed, 0 failed |
| Free sponsor sample call | HTTP 200 |
| Unpaid sponsor /brief call | HTTP 402 + exact payment offer validated |
| Mainnet x402 signed call | **NOT EXECUTED** |
| Onchain receipt for bounty eligibility | **NONE** |
| Bounty claim email | **NOT SENT** |
| New income | **0 USDC** |
| New spending | **0 USDC** |

The sponsor requires a published public repo AND a genuine paid x402 `brief` call made by this integration, evidenced by the real settlement transaction hash, before a valid claim can be sent to `partnerships@blockchainiq.co`. The first passing claim in the CrewAI/Cloudflare Agents slot wins \$125 or \$150 depending on overall claim order, and the sponsor may reject or close slots without notice. No slot is reserved by this repository.

Official docs: https://www.blockchainiq.co/agents, https://www.blockchainiq.co/api/x402/v1, https://github.com/crewAIInc/crewAI, https://github.com/x402-foundation/x402.

## License

MIT. Educational integration; not investing advice.
