/**
 * T-LAYER – Full Deployment (Escrow + TestTokens)
 *
 * Usage:
 *   npx hardhat run scripts/deploy-full.js --network bscTestnet
 *
 * Deploys:
 *   1. TestToken "tUSDT" (initial 10M to deployer)
 *   2. TestToken "tBNBT" (initial 10M to deployer)
 *   3. DarkPoolEscrow (with TEE signer)
 *   4. Mints tokens to MM bot wallet (if MM_BOT_ADDRESS set)
 */

require("dotenv").config();
const hre = require("hardhat");

async function main() {
  const { ethers, network } = hre;

  const TEE_SIGNER = process.env.TEE_SIGNER_ADDRESS;
  if (!TEE_SIGNER) throw new Error("TEE_SIGNER_ADDRESS not set in .env");

  const MM_BOT_ADDRESS = process.env.MM_BOT_ADDRESS || "";

  const [deployer] = await ethers.getSigners();
  const balance = await ethers.provider.getBalance(deployer.address);

  console.log("═══════════════════════════════════════");
  console.log("  T-LAYER – Full Deployment");
  console.log("═══════════════════════════════════════");
  console.log(`Network:          ${network.name} (chainId ${network.config.chainId})`);
  console.log(`Deployer:         ${deployer.address}`);
  console.log(`Balance:          ${ethers.formatEther(balance)} BNB`);
  console.log(`TEE Signer:       ${TEE_SIGNER}`);
  if (MM_BOT_ADDRESS) console.log(`MM Bot:           ${MM_BOT_ADDRESS}`);
  console.log("───────────────────────────────────────\n");

  const INITIAL_SUPPLY = ethers.parseEther("10000000"); // 10M tokens
  const MM_MINT_AMOUNT = ethers.parseEther("100000");   // 100K to MM bot

  // ── 1. Deploy tUSDT ──
  console.log("1/3 Deploying tUSDT...");
  const TestToken = await ethers.getContractFactory("TestToken");
  const tUSDT = await TestToken.deploy("Test USDT", "tUSDT", INITIAL_SUPPLY);
  await tUSDT.waitForDeployment();
  const tUSDTAddr = await tUSDT.getAddress();
  console.log(`  ✓ tUSDT: ${tUSDTAddr}`);

  // ── 2. Deploy tBNBT ──
  console.log("2/3 Deploying tBNBT...");
  const tBNBT = await TestToken.deploy("Test Wrapped BNB", "tBNBT", INITIAL_SUPPLY);
  await tBNBT.waitForDeployment();
  const tBNBTAddr = await tBNBT.getAddress();
  console.log(`  ✓ tBNBT: ${tBNBTAddr}`);

  // ── 3. Deploy DarkPoolEscrow ──
  console.log("3/3 Deploying DarkPoolEscrow...");
  const DarkPoolEscrow = await ethers.getContractFactory("DarkPoolEscrow");
  const escrow = await DarkPoolEscrow.deploy(TEE_SIGNER);
  await escrow.waitForDeployment();
  const escrowAddr = await escrow.getAddress();
  const deployTx = escrow.deploymentTransaction();
  console.log(`  ✓ Escrow: ${escrowAddr} (tx: ${deployTx.hash})`);

  // Verify TEE signer
  const storedSigner = await escrow.teeSignerAddress();
  console.log(`  TEE signer on-chain: ${storedSigner} ${storedSigner === TEE_SIGNER ? "✓" : "✗ MISMATCH"}`);

  // ── 4. Mint to MM bot (optional) ──
  if (MM_BOT_ADDRESS) {
    console.log(`\nMinting 100K tokens to MM bot (${MM_BOT_ADDRESS})...`);
    const tx1 = await tUSDT.mint(MM_BOT_ADDRESS, MM_MINT_AMOUNT);
    await tx1.wait();
    console.log(`  ✓ 100K tUSDT minted`);

    const tx2 = await tBNBT.mint(MM_BOT_ADDRESS, MM_MINT_AMOUNT);
    await tx2.wait();
    console.log(`  ✓ 100K tBNBT minted`);
  }

  // ── Summary ──
  console.log("\n═══════════════════════════════════════");
  console.log("  Deployment Summary");
  console.log("═══════════════════════════════════════");
  console.log(`ESCROW_CONTRACT_ADDRESS=${escrowAddr}`);
  console.log(`VITE_TOKEN_USDT=${tUSDTAddr}`);
  console.log(`VITE_TOKEN_BNB=${tBNBTAddr}`);
  console.log(`TEE_SIGNER_ADDRESS=${TEE_SIGNER}`);
  console.log("═══════════════════════════════════════");
  console.log("\nAdd these to .env (frontend + engine).");
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
