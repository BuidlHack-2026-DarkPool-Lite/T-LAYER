# 🌑 T-LAYER

**Private OTC Trading on BNB Chain, Powered by Competitive TEE Matching**

> Every on-chain order is public. Bots exploit it before you can blink.
> T-LAYER fixes this.

[![BuidlHack 2026](https://img.shields.io/badge/BuidlHack-2026-blue)]()
[![BNB Chain](https://img.shields.io/badge/BNB_Chain-Testnet-F0B90B)]()
[![NEAR AI](https://img.shields.io/badge/NEAR_AI-TEE-00C1DE)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green)]()

---

## The Problem

DeFi traders face significant losses from MEV (Maximal Extractable Value) attacks — with Flashbots data reporting **$1.3B+ extracted** from DeFi users over 2023-2025. Front-running bots monitor the public mempool and exploit pending orders before they settle. As a result, market makers often shift liquidity toward centralized venues, and traders absorb wider spreads.

## The Solution

T-LAYER is a **private OTC trading layer** on BNB Chain where order details never leak on-chain. Three AI strategies from **three different model families** compete in parallel inside a **NEAR AI Trusted Execution Environment (TEE)**. A Judge AI then scores each result on fill rate, spread, and fairness to pick the optimal match. Matched trades settle via on-chain atomic swaps.

No one — not even the server operator — can read the order book or tamper with the matching outcome.

### Key Features

- **Competitive TEE Matching** — 3 AI strategies race in parallel; a Judge scores and selects the optimal result. The outcome is provably better than the alternatives the Judge evaluated.
- **Three Different Model Families** — Qwen, GLM, and GPT-OSS compete inside the TEE. Different architectures and training data produce genuinely diverse strategies — a single model family cannot dominate.
- **Double-Layer Privacy** — Wallet addresses are stripped by the backend before orders enter the TEE. Even in the worst case where the TEE is compromised, trader identity is not exposed.
- **Real-Time Pricing Inside the Enclave** — Live price feeds from Binance, Chainlink, and PancakeSwap are accessed from within the TEE and used during matching. This is structurally difficult for ZKP-based systems.
- **Atomic Settlement** — Escrow deposit → TEE-signed match → on-chain atomic swap. Zero counterparty risk at settlement.
- **Pre-Match MEV Resistance** — Order details live only inside the TEE until the match is signed. Front-running and sandwich attacks on pending orders are structurally impossible.

---

## Architecture: Competitive TEE Matching

```
┌──────────────┐    ┌──────────────┐    ┌─────────────────────────────────────────────┐
│              │    │              │    │           NEAR AI TEE ENCLAVE               │
│  1. User     │───▶│ 2. Anonymize │───▶│                                             │
│    Order     │    │ Strip wallet │    │  ┌───────────┐┌──────────┐┌──────────────┐  │
│  MetaMask →  │    │ Order ID     │    │  │  Call 1   ││  Call 2  ││    Call 3    │  │
│  Frontend →  │    │ only         │    │  │Conservati-││  Volume  ││     Free     │  │
│  Backend API │    │              │    │  │   ve      ││   Max    ││  Optimizer   │  │
└──────────────┘    └──────────────┘    │  │ Qwen3-30B ││  GLM-5   ││ GPT OSS 120B │  │
                                        │  └─────┬─────┘└────┬─────┘└──────┬───────┘  │
                                        │        └───────────┼─────────────┘          │
                                        │                    ▼                        │
                                        │           ┌─────────────────┐               │
                                        │           │     Call 4      │  Scoring:     │
                                        │           │     JUDGE       │  Fill   40%   │
                                        │           │  Qwen3.5-122B   │  Spread 30%   │
                                        │           │ Score & Select  │  Fair   30%   │
                                        │           └────────┬────────┘               │
                                        └────────────────────┼────────────────────────┘
                                                             ▼
┌──────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│ 7. Result    │◀───│ 6. On-chain          │◀───│  5. TEE         │
│    to User   │    │    Settlement        │    │  Signature      │
│ via WebSocket│    │ executeSwap() on BSC │    │  ECDSA +        │
│ TX hash +    │    │ DarkPoolEscrow       │    │  NVIDIA GPU     │
│ Winner +     │    │                      │    │  Attestation    │
│ Score table  │    │                      │    │                 │
└──────────────┘    └──────────────────────┘    └─────────────────┘
```

### How the 4 TEE Calls Work

Each role runs on a **different TEE-protected model** inside NEAR AI Cloud for maximum diversity.

| TEE Call | Strategy | Model | Approach |
|----------|----------|-------|----------|
| **Call 1: Conservative** | Safe matching | **Qwen3-30B** | Match by smallest price gap first. If uncertain, don't match. |
| **Call 2: Volume Max** | Max fill rate | **GLM-5** | Fill as many orders as possible. Aggressive partial fills. |
| **Call 3: Free Optimizer** | LLM-driven holistic | **GPT OSS 120B** | Balance fill rate, price quality, and fairness holistically. |
| **Call 4: Judge** | Score & select | **Qwen3.5-122B** | Evaluate all 3 results on Fill Rate (40%) + Spread (30%) + Fairness (30%). Pick the winner. |

### Why Competitive > Single Matching

A single TEE matcher can only prove *"this TEE executed its logic faithfully."*
Competitive TEE matching adds a second, stronger claim: *"this result was better than the alternatives the Judge evaluated."*

---

## Privacy Design

Wallet addresses are **stripped by the backend before orders enter the TEE**:

| TEE Receives | TEE Does NOT Know |
|---|---|
| `{ id: "order-001", side: "buy", pair: "BNB/USDT", amount: 10, price: 590 }` | Wallet address (`0x7F...3b9A`), IP address, trade history |

The TEE returns `"order-001 ↔ order-003 matched"` → the backend restores order ID → wallet mapping → the TEE-signed result is submitted on-chain. Even if the TEE is compromised, trader identity is never exposed to the enclave.

---

## Why TEE Is Essential

| Attack Scenario | Without TEE | With TEE |
|---|---|---|
| Operator manipulates match results | Possible — server can modify | Impossible — execution inside TEE |
| Operator rigs Judge scores | Possible — scoring logic editable | Impossible — Judge runs inside TEE |
| Operator reads orders pre-match | Possible — server logs visible | Meaningless — wallet addresses already stripped |
| Third-party verification | "Trust me, it was fair" | Attestation report proves it |

**Key insight:** A single TEE proves fairness. Competitive TEE proves *optimality*.

---

## Why TEE over ZKP?

|  | TEE (T-LAYER) | ZKP-based approaches |
|---|---|---|
| **Real-time pricing** | Live external feeds (Binance, Chainlink, PancakeSwap) accessed from inside the enclave | Hard to incorporate external data — requires trusted oracle bridges |
| **Multi-party matching** | Native N-way match support | Extremely complex circuit design |
| **Multi-model AI matching** | 3 heterogeneous LLMs compete in parallel | Not feasible inside ZK circuits |
| **Order privacy** | Full (data lives only inside enclave) | Full (via zero-knowledge proofs) |
| **Implementation maturity for matching** | Production-ready on NEAR AI Cloud | Primarily research-stage for this use case |

T-LAYER is designed for use cases where **real-time external data access** and **multi-agent reasoning** are first-class requirements — a space where ZKP-based architectures are not yet practical.

---

## Monorepo Structure

```
T-Layer/
├── apps/
│   ├── contracts/                # Solidity (Hardhat) — 32 tests
│   │   ├── contracts/
│   │   │   ├── DarkPoolEscrow.sol   # Escrow + atomic swap + TEE sig verify
│   │   │   ├── TestToken.sol        # ERC20 test tokens (tUSDT, tBNBT)
│   │   │   └── mocks/               # MockERC20, ReentrancyAttacker
│   │   ├── scripts/
│   │   │   ├── deploy.js            # Escrow-only deploy
│   │   │   └── deploy-full.js       # Full deploy (tokens + escrow + mint)
│   │   └── test/DarkPoolEscrow.test.js
│   ├── engine/                   # Python (FastAPI + NEAR AI TEE)
│   │   └── src/
│   │       ├── matching/
│   │       │   ├── engine.py          # _competitive_match() — 3 strategies + Judge
│   │       │   ├── llm_engine.py      # TEE call functions (4 parallel calls)
│   │       │   ├── prompt.py          # Strategy-specific system prompts
│   │       │   ├── runner.py          # Matching cycle orchestrator
│   │       │   ├── validator.py       # Match result validation
│   │       │   └── schema.py          # Data models
│   │       ├── attestation/           # NEAR AI + NVIDIA GPU attestation
│   │       ├── pricing/               # Binance, Chainlink, PancakeSwap feeds
│   │       │   ├── aggregator.py      # Multi-source price aggregation
│   │       │   └── dynamic_slippage.py # Volatility-aware slippage control
│   │       ├── signer/                # ECDSA signing + BSC submission
│   │       │   ├── hash_builder.py    # EIP-191 struct hash for executeSwap
│   │       │   ├── signer.py          # TEE wallet ECDSA signing
│   │       │   ├── submitter.py       # BSC transaction broadcast
│   │       │   └── pipeline.py        # Sign → submit → broadcast pipeline
│   │       ├── mm_bot/                # Market maker bot (auto-quotes on BSC testnet)
│   │       ├── models/                # Order, OrderBook, Match data models
│   │       └── main.py / routes.py / ws.py
│   └── frontend/                 # React + Vite + wagmi
│       └── src/
│           ├── App.tsx                # Main UI + matching result display
│           ├── hooks/                 # useWallet, useEscrow
│           ├── services/              # API + WebSocket clients
│           └── config.ts / abi.ts
├── packages/contracts-abi/       # Shared ABI (single source of truth)
├── tools/                        # Dev utilities
└── .github/workflows/            # CI (path-filtered matrix)
```

---

## Live Demo

| Service | URL |
|---------|-----|
| **Frontend** | [tlayer-test1.vercel.app](https://tlayer-test1.vercel.app) |
| **Engine API** | [t-layer-production.up.railway.app](https://t-layer-production.up.railway.app) |

## Deployed Contracts (BSC Testnet)

| Contract | Address |
|----------|---------|
| **DarkPoolEscrow** | [`0xfc0279c78F800ffb963f89E507e2E6909A40d407`](https://testnet.bscscan.com/address/0xfc0279c78F800ffb963f89E507e2E6909A40d407) |
| **TestToken tUSDT** | [`0xF34fB8fDe28c4162F998Cf9B42068a828a417bC3`](https://testnet.bscscan.com/address/0xF34fB8fDe28c4162F998Cf9B42068a828a417bC3) |
| **TestToken tBNBT** | [`0x1Ef37FA15bc5933398a1177EF04302399A4588d4`](https://testnet.bscscan.com/address/0x1Ef37FA15bc5933398a1177EF04302399A4588d4) |

---

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **Python** ≥ 3.11 + [uv](https://github.com/astral-sh/uv)
- **MetaMask** wallet with BSC Testnet configured
- **tBNB** from [BNB Chain Testnet Faucet](https://www.bnbchain.org/en/testnet-faucet)

### 1. Clone & Install

```bash
git clone https://github.com/BuidlHack-2026-DarkPool-Lite/T-Layer.git
cd T-Layer
```

### 2. Deploy Contracts

```bash
cd apps/contracts
cp .env.example .env
# Edit .env:
#   DEPLOYER_PRIVATE_KEY=0x...
#   TEE_SIGNER_ADDRESS=0x... (TEE signer wallet public address)

npx hardhat run scripts/deploy-full.js --network bscTestnet
```

This deploys tUSDT + tBNBT test tokens, DarkPoolEscrow, and mints 100K tokens to the MM bot. Save the output addresses.

Optional — verify on BSCScan:
```bash
npx hardhat verify --network bscTestnet <CONTRACT_ADDRESS> <TEE_SIGNER_ADDRESS>
```

### 3. Start the Engine

```bash
cd apps/engine
cp .env.example .env
# Edit .env:
#   ESCROW_CONTRACT_ADDRESS=0x... (from step 2)
#   TEE_PRIVATE_KEY=0x... (TEE signer wallet private key)
#   BSC_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545
#   NEARAI_CLOUD_API_KEY=... (from https://app.near.ai)
#   NEAR_AI_API_KEY=... (LLM matching reasoning)

uv run uvicorn src.main:app --reload
```

> NEAR AI keys are required for competitive TEE matching (3 strategies + Judge).
> When configured, attestation shows "VERIFIED" and AI reasoning is displayed in the UI.

### 4. Start the Frontend

```bash
cd apps/frontend
cp .env.example .env
# Edit .env:
#   VITE_ESCROW_ADDRESS=0x... (from step 2)
#   VITE_TOKEN_BNB=0x... (tBNBT address from step 2)
#   VITE_TOKEN_USDT=0x... (tUSDT address from step 2)

npm install
npm run dev
```

### 5. Smoke Test

1. Open the app → Connect MetaMask (BSC Testnet)
2. Place a **buy** order for BNB → MetaMask approve + deposit
3. The built-in **MM bot** auto-places the counterparty sell order
4. Three strategies compete inside the TEE → the Judge picks the winner
5. `executeSwap` settles on-chain atomically
6. Results display across **5 paginated screens**: Trade Summary → TEE Matching → Attestation → Analysis → Privacy Report
7. Check BSCScan: only deposit and swap txs are visible — **no order information on-chain**

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Smart Contract | Solidity (Hardhat) — BSC Testnet — 32 tests |
| TEE Engine | Python, FastAPI, NEAR AI Cloud TEE |
| AI Matching | Qwen3-30B, GLM-5, GPT OSS 120B, Qwen3.5-122B (all on NEAR AI Cloud TEE) |
| Price Feeds | Binance, Chainlink oracle, PancakeSwap |
| Frontend | React, TypeScript, Vite, wagmi, viem |
| Real-time | WebSocket (FastAPI ↔ React) |
| Verification | NEAR AI attestation + NVIDIA GPU attestation + ECDSA signature recovery |
| CI | GitHub Actions (path-filtered matrix) |

---

## Scope and Limitations

We aim to be upfront about the boundaries of the current implementation:

- **Testnet-only** — All contracts are deployed to BSC Testnet. Mainnet deployment requires further audits and operational hardening.
- **End-to-end matching takes up to ~60 seconds** — This includes 4 sequential LLM calls (3 strategies + Judge), TEE signing with attestation, and on-chain settlement. T-LAYER is designed for OTC-style trades where optimal matching is more valuable than raw latency. We do not claim millisecond-level matching.
- **MEV resistance is pre-match** — Order details are hidden until the match is signed. The final settlement transaction is naturally public, consistent with how TradFi dark pools disclose executed trades.
- **MM bootstrap** — For the demo, a built-in MM bot provides initial liquidity on BSC Testnet. Production deployment would require a real market maker program, which is outside the scope of this hackathon.

---

## Team

Built at **BuidlHack 2026** — BNB Chain + NEAR AI Track.

| Name | Role | Focus |
|------|------|-------|
| **Daeyun** | PM / Pitch | Product strategy, pitch deck, submission |
| **Hyeonseung** | Lead / TEE Backend | NEAR AI Cloud + matching engine |
| **Jinsung** | Frontend | wagmi + React UX |
| **Giho** | AI Matching | Price feeds + matching logic |
| **Seungjae** | Contract Lead | Solidity escrow + atomic swap |

---

## Links

- [Live Demo](https://tlayer-test1.vercel.app)
- [GitHub](https://github.com/BuidlHack-2026-DarkPool-Lite/T-LAYER)
- [Demo Video](https://www.youtube.com/watch?v=DU6H3VlQrfU)

---

## License

MIT
