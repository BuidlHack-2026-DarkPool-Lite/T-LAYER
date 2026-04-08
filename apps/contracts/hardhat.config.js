require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const DEPLOYER_PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY || "0x" + "0".repeat(64);

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: false,
      // OZ v5.6+ uses mcopy (EIP-5656) which requires Cancun EVM.
      // BSC has supported Cancun since its Maxwell hard fork.
      evmVersion: "cancun",
    },
  },

  networks: {
    // ── 로컬 테스트
    hardhat: {
      chainId: 31337,
    },

    // ── BSC Testnet (chainId 97)
    bscTestnet: {
      url: "https://data-seed-prebsc-1-s1.binance.org:8545/",
      chainId: 97,
      accounts: [DEPLOYER_PRIVATE_KEY],
      gasPrice: 10_000_000_000, // 10 gwei
    },

    // ── opBNB Testnet (chainId 5611)
    opBNBTestnet: {
      url: "https://opbnb-testnet-rpc.bnbchain.org",
      chainId: 5611,
      accounts: [DEPLOYER_PRIVATE_KEY],
      gasPrice: 1_000_000, // 0.001 gwei (opBNB is very cheap)
    },
  },

  etherscan: {
    apiKey: {
      bscTestnet: process.env.BSCSCAN_API_KEY || "",
      // opBNB testnet verification (uses opBNBScan)
      opBNBTestnet: process.env.OPBNBSCAN_API_KEY || "",
    },
    customChains: [
      {
        network: "opBNBTestnet",
        chainId: 5611,
        urls: {
          apiURL: "https://api-opbnb-testnet.bscscan.com/api",
          browserURL: "https://opbnb-testnet.bscscan.com",
        },
      },
    ],
  },

  gasReporter: {
    enabled: true,
    currency: "USD",
  },
};
