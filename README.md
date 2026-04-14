# 🌑 DarkPool Lite

**MEV-Protected OTC Trading on BNB Chain, Powered by Competitive TEE Matching + AI**

> Every on-chain order is public. Bots exploit it before you can blink.
> DarkPool Lite fixes this.

[![BuidlHack 2026](https://img.shields.io/badge/BuidlHack-2026-blue)]()
[![BNB Chain](https://img.shields.io/badge/BNB_Chain-Testnet-F0B90B)]()
[![NEAR AI](https://img.shields.io/badge/NEAR_AI-TEE-00C1DE)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green)]()

---

## The Problem

DeFi traders lose **$1.3B+** to MEV (Maximal Extractable Value) attacks annually. Front-running bots watch the public mempool and exploit pending orders before they settle. Market makers flee to centralized exchanges, liquidity dries up, and spreads widen — everyday traders pay the price.

## The Solution

DarkPool Lite is a **decentralized dark pool** for MEV-free OTC trading on BNB Chain. Three competing AI strategies match orders inside a **NEAR AI Trusted Execution Environment (TEE)**, a Judge AI picks the optimal result, and matched trades settle via **on-chain atomic swaps**. No one — not even the server operator — can see the order book or tamper with matching results.

### Key Features

- **Competitive TEE Matching** — 3 AI strategies race in parallel; a Judge scores and selects the best result. Proves the outcome is better than alternatives.
- **Double-Layer Privacy** — Wallet addresses are stripped before entering the TEE. Even if the TEE is compromised, trader identity stays hidden.
- **AI-Powered Pricing** — Real-time fair price aggregated from PancakeSwap & Binance with dynamic slippage guardrails.
- **Atomic Settlement** — Escrow deposit → TEE-signed match → on-chain atomic swap. Zero counterparty risk.
- **MEV Structural Impossibility** — Not just mitigation — MEV is architecturally impossible because order data only exists inside the TEE.

---

## Architecture: Competitive TEE Matching

```
┌──────────────┐    ┌──────────────┐    ┌─────────────────────────────────────────────┐
│              │    │              │    │           NEAR AI TEE ENCLAVE               │
│  1. User     │───▶│ 2. Anonymize │───▶│                                             │
│  Order       │    │  Strip wallet│    │  ┌────────────┐┌────────────┐┌────────────┐ │
│  MetaMask →  │    │  Order ID    │    │  │ TEE Call 1 ││ TEE Call 2 ││ TEE Call 3 │ │
│  Frontend →  │    │  only        │    │  │Conservative││ Volume Max ││   Free     │ │
│  Backend API │    │              │    │  │Safe matching││Max fill    ││ Optimizer  │ │
└──────────────┘    └──────────────┘    │  │            ││ rate       ││LLM decides │ │
                                        │  └─────┬──────┘└─────┬──────┘└─────┬──────┘ │
                                        │        └─────────────┼─────────────┘        │
                                        │                      ▼                      │
                                        │             ┌──────────────┐                │
                                        │             │  TEE Call 4  │  Scoring:      │
                                        │             │    JUDGE     │  Fill Rate 40% │
                                        │             │ Score &      │  Spread    30% │
                                        │             │ Select Winner│  Fairness  30% │
                                        │             └──────┬───────┘                │
                                        └────────────────────┼────────────────────────┘
                                                             ▼
┌──────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│ 7. Result    │◀───│ 6. On-chain          │◀───│ 5. TEE          │
│ to User      │    │ Settlement           │    │ Signature       │
│ TX hash +    │    │ executeSwap() on BSC │    │ ECDSA +         │
│ Winner +     │    │ DarkPoolEscrow       │    │ Attestation     │
│ Score table  │    │                      │    │                 │
└──────────────┘    └──────────────────────┘    └─────────────────┘
```

### How the 4 TEE Calls Work

All calls run on **DeepSeek-V3.1** inside the same NEAR AI TEE. Only the prompt differs.

| TEE Call | Strategy | Approach |
|----------|----------|----------|
| **Call 1: Conservative** | Safe matching | Match by smallest price gap first. If uncertain, don't match. |
| **Call 2: Volume Max** | Max fill rate | Fill as many orders as possible. Aggressive partial fills. |
| **Call 3: Free Optimizer** | LLM decides | Balance fill rate, price quality, and fairness holistically. |
| **Call 4: Judge** | Score & select | Evaluate all 3 results: Fill Rate (40%) + Spread (30%) + Fairness (30%). Pick the winner. |

### Why Competitive > Single Matching

A single TEE matcher can only prove *"this TEE was fair."*
Competitive TEE matching proves *"this result was **better** than the alternatives."*

---

## Privacy Design

Wallet addresses are **stripped before entering the TEE**:

| TEE Receives | TEE Does NOT Know |
|---|---|
| `{ id: "order-001", side: "buy", pair: "BNB/USDT", amount: 10, price: 590 }` | Wallet address (`0x7F...3b9A`), IP address, trade history |

The TEE returns `"order-001 ↔ order-003 matched"` → Backend restores order ID → wallet mapping → executes on-chain. Even if the TEE is compromised, trader identity is never exposed.

---

## Monorepo Structure

```
darkpool-lite/
├── apps/
│   ├── contracts/                # Solidity (Hardhat) — 32 tests
│   │   ├── contracts/
│   │   │   ├── DarkPoolEscrow.sol
│   │   │   └── mocks/           # MockERC20, ReentrancyAttacker
│   │   ├── scripts/deploy.js
│   │   └── test/DarkPoolEscrow.test.js
│   ├── engine/                   # Python (FastAPI + NEAR AI TEE)
│   │   └── src/
│   │       ├── matching/
│   │       │   ├── engine.py          # _dual_pass() → _competitive_match()
│   │       │   ├── llm_engine.py      # LLM call functions (competitive 4-call)
│   │       │   ├── prompt.py          # Strategy-specific system prompts
│   │       │   ├── rules_engine.py    # Fallback rule-based matcher
│   │       │   ├── runner.py          # Matching cycle orchestrator
│   │       │   ├── validator.py       # Match result validation
│   │       │   └── schema.py          # Data models
│   │       ├── attestation/           # NEAR AI TEE attestation verification
│   │       ├── pricing/               # PancakeSwap + Binance price feeds
│   │       ├── signer/                # ECDSA signing for BSC submission
│   │       ├── mm_bot/                # Market maker bot (disabled in demo)
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

## Deployed Contracts (BSC Testnet)

| Contract | Address |
|----------|---------|
| **DarkPoolEscrow** | `0x34336C18E764B2ae28d28E90E040E57d6C74DAce` |
| **TestToken tUSDT** | `0xb8880f6c5D256263576266d90E9C20e85fD9F40E` |
| **TestToken tBNBT** | `0x70F2b66CD95F82389c3382c6FDB7E0e4A2CA4f62` |

---

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **Python** ≥ 3.11 + [uv](https://github.com/astral-sh/uv)
- **MetaMask** wallet with BSC Testnet configured
- **tBNB** from [BNB Chain Testnet Faucet](https://www.bnbchain.org/en/testnet-faucet)

### 1. Clone & Install

```bash
git clone https://github.com/BuidlHack-2026-DarkPool-Lite/darkpool-lite.git
cd darkpool-lite
```

### 2. Deploy Contracts

```bash
cd apps/contracts
cp .env.example .env
# Edit .env:
#   DEPLOYER_PRIVATE_KEY=0x...
#   TEE_SIGNER_ADDRESS=0x... (TEE signer wallet public address)

npx hardhat run scripts/deploy.js --network bscTestnet
```

Save the deployed contract address — you'll need it for the next steps.

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
#   NEARAI_CLOUD_API_KEY=... (optional, from https://app.near.ai)
#   NEAR_AI_API_KEY=... (optional, for LLM matching reasoning)

uv run uvicorn src.main:app --reload
```

> **Without NEAR AI keys:** Demo still works — attestation shows "UNVERIFIED" and matching uses the rule engine fallback.
> **With NEAR AI keys:** Attestation shows "VERIFIED" + competitive 3-strategy matching with Judge scoring + AI reasoning displayed in UI.

### 4. Start the Frontend

```bash
cd apps/frontend
cp .env.example .env
# Edit .env:
#   VITE_ESCROW_ADDRESS=0x... (from step 2)
#   VITE_TOKEN_BNB=0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd

npm install
npm run dev
```

### 5. Smoke Test

1. Open the app → Connect MetaMask (BSC Testnet)
2. **Tab 1 (Bob / MM):** Place a buy order for 100 BNB → approve + deposit
3. **Tab 2 (Alice / Trader):** Place a sell order for 80 BNB → approve + deposit
4. Watch 3 strategies compete inside the TEE → Judge picks the winner
5. Atomic swap executes on-chain
6. Check BSCScan: only deposit and swap txs visible — **no order info on-chain**
7. Bob's remaining 20 BNB stays in the pool (partial fill)

---

## Why TEE Is Essential

| Attack Scenario | Without TEE | With TEE |
|---|---|---|
| Operator manipulates match results | Possible — server can modify | Impossible — execution inside TEE |
| Operator rigs Judge scores | Possible — scoring logic editable | Impossible — Judge runs inside TEE |
| Operator reads orders pre-match | Possible — server logs visible | Meaningless — wallet addresses stripped |
| Third-party verification | "Trust me, it was fair" | Attestation report proves it |

**Key insight:** A single TEE proves fairness. Competitive TEE proves *optimality*.

---

## Why TEE over ZKP?

| | TEE (DarkPool Lite) | ZKP |
|---|---|---|
| Matching latency | Milliseconds | Seconds to minutes (proof generation) |
| Multi-party matching | Native support | Extremely complex circuits |
| Real-time pricing | Live DEX feeds inside enclave | Hard to incorporate external data |
| Competitive strategies | Multiple LLMs in parallel | Not feasible with ZK circuits |
| Implementation complexity | Production-ready (NEAR AI Cloud) | Research-stage for matching |

---

## Market Maker Incentive

Traditional DEX market makers lose spread profits to sandwich bots. In DarkPool Lite, order data lives exclusively inside the TEE — MEV is **structurally impossible**. This protected spread is the core incentive for MM participation.

**Roadmap:**
- **MVP** — Team acts as MM for demo
- **Phase 2** — 0.1% per-trade fee + MM rebate + priority matching
- **Phase 3** — LP pool: MM 40% / LP 40% / Protocol 20%

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Smart Contract | Solidity (Hardhat) — BSC Testnet |
| TEE Engine | Python, FastAPI, NEAR AI Cloud TEE |
| AI Matching | DeepSeek-V3.1 × 4 calls (3 strategies + 1 judge) |
| AI Pricing | Multi-source aggregation (PancakeSwap, Binance) |
| Frontend | React, TypeScript, Vite, wagmi, ethers.js |
| Verification | NEAR AI attestation + NVIDIA GPU attestation |
| CI | GitHub Actions (path-filtered matrix) |

---

## Team

Built at **BuidlHack 2026** — BNB Chain + NEAR AI Track.

| Name | Role | Focus |
|------|------|-------|
| Daeyun | PM / Pitch | Product strategy + pitch deck + submission |
| Hyunseung | Lead / TEE Backend | NEAR AI Cloud + matching engine |
| Jinsung | Frontend | wagmi + React UX |
| Kiho | AI Matching | Price feed + optimization |
| Seungjae | Contract Lead | Solidity escrow + atomic swap |

---

## Links

- 🎬 [Demo Video](#) <!-- TODO: insert link -->
- 📊 [Pitch Deck](#) <!-- TODO: insert link -->
- 🐦 [Tweet](#) <!-- TODO: insert link -->

---

## License

MIT
