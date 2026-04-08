/**
 * DarkPool Lite – Deployment Script
 *
 * Usage:
 *   npx hardhat run scripts/deploy.js --network bscTestnet
 *   npx hardhat run scripts/deploy.js --network opBNBTestnet
 *
 * Required env vars (.env):
 *   DEPLOYER_PRIVATE_KEY   – deployer wallet private key
 *   TEE_SIGNER_ADDRESS     – Ethereum address of the TEE signing key
 *
 * Optional:
 *   BSCSCAN_API_KEY / OPBNBSCAN_API_KEY – for auto-verification on BSCScan
 */

require("dotenv").config();
const hre = require("hardhat");

async function main() {
  const { ethers, network } = hre;

  // ── Validate env ──────────────────────────────────────────────────────────
  const TEE_SIGNER = process.env.TEE_SIGNER_ADDRESS;
  if (!TEE_SIGNER || TEE_SIGNER === "0xTEE_SIGNER_ADDRESS_HERE") {
    throw new Error(
      "TEE_SIGNER_ADDRESS is not set in .env.\n" +
      "Generate a dedicated ECDSA keypair inside the TEE and paste the address here."
    );
  }

  const [deployer] = await ethers.getSigners();
  const balance = await ethers.provider.getBalance(deployer.address);

  console.log("═══════════════════════════════════════");
  console.log("  DarkPool Lite – Contract Deployment  ");
  console.log("═══════════════════════════════════════");
  console.log(`Network:         ${network.name} (chainId ${network.config.chainId})`);
  console.log(`Deployer:        ${deployer.address}`);
  console.log(`Deployer balance: ${ethers.formatEther(balance)} BNB`);
  console.log(`TEE Signer:      ${TEE_SIGNER}`);
  console.log("───────────────────────────────────────");

  // ── Deploy ────────────────────────────────────────────────────────────────
  console.log("\nDeploying DarkPoolEscrow...");
  const DarkPoolEscrow = await ethers.getContractFactory("DarkPoolEscrow");
  const escrow = await DarkPoolEscrow.deploy(TEE_SIGNER);
  await escrow.waitForDeployment();

  const address = await escrow.getAddress();
  const deployTx = escrow.deploymentTransaction();

  console.log(`\n✓ DarkPoolEscrow deployed!`);
  console.log(`  Address:  ${address}`);
  console.log(`  Tx hash:  ${deployTx.hash}`);

  // ── Verify constructor state ──────────────────────────────────────────────
  const storedSigner = await escrow.teeSignerAddress();
  console.log(`  TEE signer on-chain: ${storedSigner}`);
  console.log(storedSigner === TEE_SIGNER ? "  ✓ TEE signer matches" : "  ✗ Mismatch!");

  // ── Block explorer link ───────────────────────────────────────────────────
  const explorers = {
    bscTestnet:    `https://testnet.bscscan.com/address/${address}`,
    opBNBTestnet:  `https://opbnb-testnet.bscscan.com/address/${address}`,
  };
  if (explorers[network.name]) {
    console.log(`\n  Explorer: ${explorers[network.name]}`);
  }

  // ── Auto-verify on BSCScan (requires API key) ─────────────────────────────
  if (network.name !== "hardhat" && network.name !== "localhost") {
    console.log("\nWaiting 5 confirmations before verification...");
    await deployTx.wait(5);

    try {
      console.log("Submitting source code to block explorer...");
      await hre.run("verify:verify", {
        address:              address,
        constructorArguments: [TEE_SIGNER],
      });
      console.log("✓ Contract verified!");
    } catch (err) {
      if (err.message.includes("Already Verified")) {
        console.log("✓ Already verified.");
      } else {
        console.warn("⚠ Verification failed:", err.message);
        console.warn("  Run manually:");
        console.warn(`  npx hardhat verify --network ${network.name} ${address} ${TEE_SIGNER}`);
      }
    }
  }

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("\n═══════════════════════════════════════");
  console.log("  Deployment Summary");
  console.log("═══════════════════════════════════════");
  console.log(`ESCROW_CONTRACT_ADDRESS=${address}`);
  console.log(`TEE_SIGNER_ADDRESS=${TEE_SIGNER}`);
  console.log("Add these to your .env (frontend + TEE backend).");
  console.log("═══════════════════════════════════════");
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
