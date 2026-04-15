const hre = require("hardhat");

async function main() {
  const [sender] = await hre.ethers.getSigners();
  const target = process.env.TARGET || "0xcb33486aa219Fb6C7380aC11aa743428aB284962";
  const amount = hre.ethers.parseEther(process.env.AMOUNT || "0.05");

  const balBefore = await hre.ethers.provider.getBalance(sender.address);
  console.log(`Sender: ${sender.address}`);
  console.log(`Sender balance: ${hre.ethers.formatEther(balBefore)} tBNB`);
  console.log(`Sending ${hre.ethers.formatEther(amount)} tBNB → ${target}`);

  const tx = await sender.sendTransaction({ to: target, value: amount });
  console.log(`tx: ${tx.hash}`);
  const rx = await tx.wait();
  console.log(`mined in block ${rx.blockNumber}`);

  const balAfter = await hre.ethers.provider.getBalance(target);
  console.log(`Target balance now: ${hre.ethers.formatEther(balAfter)} tBNB`);
}

main().catch((e) => { console.error(e); process.exit(1); });
