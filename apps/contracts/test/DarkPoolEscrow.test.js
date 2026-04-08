/**
 * DarkPool Lite – DarkPoolEscrow v2 Test Suite
 *
 * v2 changes tested:
 *  - 선예치 (pre-deposit before matching)
 *  - 부분체결 (partial fills)
 *  - 잔량 환불 / 취소 (cancel with remainder refund)
 *  - 수수료 수집 (P1 fee collection)
 *
 * Coverage:
 *  ① Deployment & TEE signer management          (P0)
 *  ② deposit – 선예치                             (P0)
 *  ③ executeSwap – full fill                     (P0)
 *  ④ executeSwap – partial fill (부분체결)         (P0)
 *  ⑤ cancelOrder – 잔량 환불 / 취소               (P0)
 *  ⑥ Fee collection (수수료)                      (P1)
 *  ⑦ Security – signature, replay, reentrancy    (P1)
 */

const { expect }      = require("chai");
const { ethers }      = require("hardhat");
const { time }        = require("@nomicfoundation/hardhat-network-helpers");

// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Sign a swap execution with the TEE private key.
 * Matches DarkPoolEscrow.getSwapStructHash() + EIP-191 prefix.
 */
async function signSwap(teeSigner, escrowAddress, chainId, params) {
  const { swapId, makerOrderId, takerOrderId, makerFillAmount, takerFillAmount } = params;
  const structHash = ethers.solidityPackedKeccak256(
    ["uint256", "address", "bytes32", "bytes32", "bytes32", "uint256", "uint256"],
    [chainId, escrowAddress, swapId, makerOrderId, takerOrderId, makerFillAmount, takerFillAmount]
  );
  return teeSigner.signMessage(ethers.getBytes(structHash));
}

// ─────────────────────────────────────────────────────────────────────────────
//  Test Suite
// ─────────────────────────────────────────────────────────────────────────────

describe("DarkPoolEscrow v2", function () {
  let escrow, escrowAddr;
  let tokenA, tokenB;
  let owner, alice, bob, attacker, anyone;
  let teeSigner;
  let chainId;

  const MINT = ethers.parseEther("10000");
  const HUNDRED = ethers.parseEther("100");
  const EIGHTY  = ethers.parseEther("80");
  const SIXTY   = ethers.parseEther("60");
  const FIFTY   = ethers.parseEther("50");
  const FORTY   = ethers.parseEther("40");
  const TWENTY  = ethers.parseEther("20");

  beforeEach(async function () {
    [owner, alice, bob, attacker, anyone] = await ethers.getSigners();
    teeSigner = ethers.Wallet.createRandom().connect(ethers.provider);
    chainId   = (await ethers.provider.getNetwork()).chainId;

    const Mock = await ethers.getContractFactory("MockERC20");
    tokenA = await Mock.deploy("Token A", "TKA", 18);
    tokenB = await Mock.deploy("Token B", "TKB", 18);

    const Escrow = await ethers.getContractFactory("DarkPoolEscrow");
    escrow = await Escrow.deploy(teeSigner.address);
    escrowAddr = await escrow.getAddress();

    await tokenA.mint(alice.address, MINT);
    await tokenB.mint(bob.address,   MINT);

    await tokenA.connect(alice).approve(escrowAddr, ethers.MaxUint256);
    await tokenB.connect(bob).approve(escrowAddr, ethers.MaxUint256);
  });

  // ── Utility: deposit + sign + execute in one call ─────────────────────────

  /** Deposit for alice (maker) and bob (taker), return order IDs. */
  async function depositBoth(makerAmt = HUNDRED, takerAmt = FIFTY) {
    const makerOrderId = ethers.randomBytes(32);
    const takerOrderId = ethers.randomBytes(32);
    const tokenAAddr   = await tokenA.getAddress();
    const tokenBAddr   = await tokenB.getAddress();

    await escrow.connect(alice).deposit(makerOrderId, tokenAAddr, makerAmt);
    await escrow.connect(bob).deposit(takerOrderId, tokenBAddr, takerAmt);

    return { makerOrderId, takerOrderId, tokenAAddr, tokenBAddr };
  }

  /** Create TEE-signed swap params. */
  async function buildSwap(overrides = {}) {
    const swapId          = overrides.swapId          ?? ethers.randomBytes(32);
    const makerOrderId    = overrides.makerOrderId    ?? ethers.randomBytes(32);
    const takerOrderId    = overrides.takerOrderId    ?? ethers.randomBytes(32);
    const makerFillAmount = overrides.makerFillAmount ?? HUNDRED;
    const takerFillAmount = overrides.takerFillAmount ?? FIFTY;
    const signer          = overrides.signer          ?? teeSigner;

    const sig = await signSwap(signer, escrowAddr, chainId, {
      swapId, makerOrderId, takerOrderId, makerFillAmount, takerFillAmount,
    });

    return { swapId, makerOrderId, takerOrderId, makerFillAmount, takerFillAmount, sig };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ① Deployment & TEE signer management  (P0)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("① Deployment & TEE signer (P0)", function () {
    it("stores initial TEE signer address", async function () {
      expect(await escrow.teeSignerAddress()).to.equal(teeSigner.address);
    });

    it("fee is disabled by default", async function () {
      expect(await escrow.feeEnabled()).to.equal(false);
    });

    it("owner can update TEE signer", async function () {
      const newAddr = ethers.Wallet.createRandom().address;
      await expect(escrow.connect(owner).updateTEESignerAddress(newAddr))
        .to.emit(escrow, "TEESignerUpdated")
        .withArgs(teeSigner.address, newAddr);
      expect(await escrow.teeSignerAddress()).to.equal(newAddr);
    });

    it("non-owner cannot update TEE signer", async function () {
      await expect(
        escrow.connect(attacker).updateTEESignerAddress(attacker.address)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    });

    it("cannot set zero TEE signer", async function () {
      await expect(
        escrow.connect(owner).updateTEESignerAddress(ethers.ZeroAddress)
      ).to.be.revertedWith("DPE: zero address");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ② deposit (선예치)  (P0)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("② deposit – 선예치 (P0)", function () {
    it("creates order and locks tokens in contract", async function () {
      const orderId  = ethers.randomBytes(32);
      const tokenAddr = await tokenA.getAddress();

      await expect(escrow.connect(alice).deposit(orderId, tokenAddr, HUNDRED))
        .to.emit(escrow, "Deposited")
        .withArgs(orderId, alice.address, tokenAddr, HUNDRED);

      // Tokens moved from alice to escrow
      expect(await tokenA.balanceOf(alice.address)).to.equal(MINT - HUNDRED);
      expect(await tokenA.balanceOf(escrowAddr)).to.equal(HUNDRED);

      // Order state
      const o = await escrow.orders(orderId);
      expect(o.trader).to.equal(alice.address);
      expect(o.token).to.equal(tokenAddr);
      expect(o.totalAmount).to.equal(HUNDRED);
      expect(o.filledAmount).to.equal(0n);
      expect(o.active).to.be.true;
    });

    it("rejects duplicate order ID", async function () {
      const orderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(orderId, await tokenA.getAddress(), HUNDRED);
      await expect(
        escrow.connect(bob).deposit(orderId, await tokenB.getAddress(), FIFTY)
      ).to.be.revertedWith("DPE: order exists");
    });

    it("rejects zero token address", async function () {
      await expect(
        escrow.connect(alice).deposit(ethers.randomBytes(32), ethers.ZeroAddress, HUNDRED)
      ).to.be.revertedWith("DPE: zero token");
    });

    it("rejects zero amount", async function () {
      await expect(
        escrow.connect(alice).deposit(ethers.randomBytes(32), await tokenA.getAddress(), 0)
      ).to.be.revertedWith("DPE: zero amount");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ③ executeSwap – full fill  (P0)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("③ executeSwap – full fill (P0)", function () {
    it("swaps tokens atomically (Alice ↔ Bob)", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);

      const swap = await buildSwap({
        makerOrderId, takerOrderId,
        makerFillAmount: HUNDRED,
        takerFillAmount: FIFTY,
      });

      const aliceBBefore = await tokenB.balanceOf(alice.address);
      const bobABefore   = await tokenA.balanceOf(bob.address);

      await expect(
        escrow.connect(anyone).executeSwap(
          swap.swapId, swap.makerOrderId, swap.takerOrderId,
          swap.makerFillAmount, swap.takerFillAmount, swap.sig
        )
      ).to.emit(escrow, "SwapExecuted")
       .withArgs(swap.swapId, makerOrderId, takerOrderId, HUNDRED, FIFTY);

      // Alice gets Bob's Token B; Bob gets Alice's Token A
      expect(await tokenB.balanceOf(alice.address)).to.equal(aliceBBefore + FIFTY);
      expect(await tokenA.balanceOf(bob.address)).to.equal(bobABefore + HUNDRED);

      // Orders deactivated (fully filled)
      expect((await escrow.orders(makerOrderId)).active).to.be.false;
      expect((await escrow.orders(takerOrderId)).active).to.be.false;
    });

    it("Maker→Contract→Taker: escrow balance returns to 0", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);
      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });

      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      expect(await tokenA.balanceOf(escrowAddr)).to.equal(0n);
      expect(await tokenB.balanceOf(escrowAddr)).to.equal(0n);
    });

    it("anyone can trigger executeSwap (permissionless)", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth();
      const swap = await buildSwap({ makerOrderId, takerOrderId });
      await expect(
        escrow.connect(anyone).executeSwap(
          swap.swapId, swap.makerOrderId, swap.takerOrderId,
          swap.makerFillAmount, swap.takerFillAmount, swap.sig
        )
      ).to.emit(escrow, "SwapExecuted");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ④ executeSwap – partial fill (부분체결)  (P0)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("④ executeSwap – partial fill 부분체결 (P0)", function () {
    it("partial fill: 100 sell vs 60 buy → 60 filled, 40 remains", async function () {
      // MM(Bob) deposits 60 Token B, Alice deposits 100 Token A
      const makerOrderId = ethers.randomBytes(32);
      const takerOrderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(makerOrderId, await tokenA.getAddress(), HUNDRED);
      await escrow.connect(bob).deposit(takerOrderId, await tokenB.getAddress(), SIXTY);

      // TEE matches: 60 Token A for 60 Token B (partial fill on maker side)
      const swap = await buildSwap({
        makerOrderId, takerOrderId,
        makerFillAmount: SIXTY,   // only 60 of Alice's 100
        takerFillAmount: SIXTY,   // all of Bob's 60
      });

      const tx = escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      await expect(tx)
        .to.emit(escrow, "SwapExecuted")
        .withArgs(swap.swapId, makerOrderId, takerOrderId, SIXTY, SIXTY);

      await expect(tx)
        .to.emit(escrow, "PartialFill")
        .withArgs(makerOrderId, SIXTY, FORTY); // 60 filled, 40 remaining

      // Maker order: still active with 40 remaining
      const maker = await escrow.orders(makerOrderId);
      expect(maker.active).to.be.true;
      expect(maker.filledAmount).to.equal(SIXTY);
      expect(await escrow.getOrderRemaining(makerOrderId)).to.equal(FORTY);

      // Taker order: fully filled, deactivated
      const taker = await escrow.orders(takerOrderId);
      expect(taker.active).to.be.false;
      expect(taker.filledAmount).to.equal(SIXTY);
    });

    it("multiple partial fills on same order", async function () {
      const makerOrderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(makerOrderId, await tokenA.getAddress(), HUNDRED);

      // First fill: 60
      const takerOrderId1 = ethers.randomBytes(32);
      await escrow.connect(bob).deposit(takerOrderId1, await tokenB.getAddress(), SIXTY);

      const swap1 = await buildSwap({
        makerOrderId, takerOrderId: takerOrderId1,
        makerFillAmount: SIXTY, takerFillAmount: SIXTY,
      });
      await escrow.connect(anyone).executeSwap(
        swap1.swapId, swap1.makerOrderId, swap1.takerOrderId,
        swap1.makerFillAmount, swap1.takerFillAmount, swap1.sig
      );

      expect((await escrow.orders(makerOrderId)).filledAmount).to.equal(SIXTY);
      expect((await escrow.orders(makerOrderId)).active).to.be.true;

      // Second fill: remaining 40
      // Bob deposits more Token B
      const takerOrderId2 = ethers.randomBytes(32);
      await escrow.connect(bob).deposit(takerOrderId2, await tokenB.getAddress(), FORTY);

      const swap2 = await buildSwap({
        makerOrderId, takerOrderId: takerOrderId2,
        makerFillAmount: FORTY, takerFillAmount: FORTY,
      });
      await escrow.connect(anyone).executeSwap(
        swap2.swapId, swap2.makerOrderId, swap2.takerOrderId,
        swap2.makerFillAmount, swap2.takerFillAmount, swap2.sig
      );

      // Now fully filled
      expect((await escrow.orders(makerOrderId)).filledAmount).to.equal(HUNDRED);
      expect((await escrow.orders(makerOrderId)).active).to.be.false;
    });

    it("fill exceeding remaining reverts", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);

      // Try to fill 200 from a 100 order
      const swap = await buildSwap({
        makerOrderId, takerOrderId,
        makerFillAmount: ethers.parseEther("200"),
        takerFillAmount: FIFTY,
      });
      await expect(
        escrow.connect(anyone).executeSwap(
          swap.swapId, swap.makerOrderId, swap.takerOrderId,
          swap.makerFillAmount, swap.takerFillAmount, swap.sig
        )
      ).to.be.revertedWith("DPE: maker fill exceeds remaining");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ⑤ cancelOrder – 잔량 환불 / 취소  (P0)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("⑤ cancelOrder – 잔량 환불 (P0)", function () {
    it("full cancel: refunds entire deposit", async function () {
      const orderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(orderId, await tokenA.getAddress(), HUNDRED);

      const balBefore = await tokenA.balanceOf(alice.address);

      await expect(escrow.connect(alice).cancelOrder(orderId))
        .to.emit(escrow, "Cancelled")
        .withArgs(orderId, alice.address, HUNDRED);

      expect(await tokenA.balanceOf(alice.address)).to.equal(balBefore + HUNDRED);
      expect((await escrow.orders(orderId)).active).to.be.false;
    });

    it("partial cancel: refunds only unfilled remainder", async function () {
      // Deposit 100, fill 60, cancel → refund 40
      const makerOrderId = ethers.randomBytes(32);
      const takerOrderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(makerOrderId, await tokenA.getAddress(), HUNDRED);
      await escrow.connect(bob).deposit(takerOrderId, await tokenB.getAddress(), SIXTY);

      const swap = await buildSwap({
        makerOrderId, takerOrderId,
        makerFillAmount: SIXTY, takerFillAmount: SIXTY,
      });
      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      const balBefore = await tokenA.balanceOf(alice.address);

      await expect(escrow.connect(alice).cancelOrder(makerOrderId))
        .to.emit(escrow, "Cancelled")
        .withArgs(makerOrderId, alice.address, FORTY); // refund 40

      expect(await tokenA.balanceOf(alice.address)).to.equal(balBefore + FORTY);
    });

    it("only order owner can cancel", async function () {
      const orderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(orderId, await tokenA.getAddress(), HUNDRED);
      await expect(
        escrow.connect(attacker).cancelOrder(orderId)
      ).to.be.revertedWith("DPE: not order owner");
    });

    it("cannot cancel already-cancelled order", async function () {
      const orderId = ethers.randomBytes(32);
      await escrow.connect(alice).deposit(orderId, await tokenA.getAddress(), HUNDRED);
      await escrow.connect(alice).cancelOrder(orderId);
      await expect(
        escrow.connect(alice).cancelOrder(orderId)
      ).to.be.revertedWith("DPE: order not active");
    });

    it("cannot cancel fully-filled order", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);
      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });

      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      await expect(
        escrow.connect(alice).cancelOrder(makerOrderId)
      ).to.be.revertedWith("DPE: order not active");
    });

    it("cannot execute on cancelled order", async function () {
      const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);

      // Alice cancels before swap
      await escrow.connect(alice).cancelOrder(makerOrderId);

      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });
      await expect(
        escrow.connect(anyone).executeSwap(
          swap.swapId, swap.makerOrderId, swap.takerOrderId,
          swap.makerFillAmount, swap.takerFillAmount, swap.sig
        )
      ).to.be.revertedWith("DPE: maker order not active");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ⑥ Fee collection 수수료  (P1)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("⑥ Fee collection (P1)", function () {
    it("no fee deducted when feeEnabled=false (default)", async function () {
      const { makerOrderId, takerOrderId, tokenAAddr, tokenBAddr } = await depositBoth(HUNDRED, FIFTY);
      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });

      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      // Bob gets full 100 Token A, Alice gets full 50 Token B
      expect(await tokenA.balanceOf(bob.address)).to.equal(HUNDRED);
      expect(await tokenB.balanceOf(alice.address)).to.equal(FIFTY);
      expect(await escrow.collectedFees(tokenAAddr)).to.equal(0n);
    });

    it("0.1% fee deducted when feeEnabled=true", async function () {
      await escrow.connect(owner).setFeeEnabled(true);

      const { makerOrderId, takerOrderId, tokenAAddr, tokenBAddr } = await depositBoth(HUNDRED, FIFTY);
      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });

      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      // Fee = 0.1% = 10 bps
      const makerFee = HUNDRED * 10n / 10000n;  // 0.01 ether
      const takerFee = FIFTY * 10n / 10000n;    // 0.005 ether

      expect(await tokenA.balanceOf(bob.address)).to.equal(HUNDRED - makerFee);
      expect(await tokenB.balanceOf(alice.address)).to.equal(FIFTY - takerFee);
      expect(await escrow.collectedFees(tokenAAddr)).to.equal(makerFee);
      expect(await escrow.collectedFees(tokenBAddr)).to.equal(takerFee);
    });

    it("owner can withdraw accumulated fees", async function () {
      await escrow.connect(owner).setFeeEnabled(true);

      const { makerOrderId, takerOrderId, tokenAAddr } = await depositBoth(HUNDRED, FIFTY);
      const swap = await buildSwap({ makerOrderId, takerOrderId, makerFillAmount: HUNDRED, takerFillAmount: FIFTY });

      await escrow.connect(anyone).executeSwap(
        swap.swapId, swap.makerOrderId, swap.takerOrderId,
        swap.makerFillAmount, swap.takerFillAmount, swap.sig
      );

      const fee = HUNDRED * 10n / 10000n;
      const ownerBefore = await tokenA.balanceOf(owner.address);

      await escrow.connect(owner).withdrawFees(tokenAAddr, owner.address);

      expect(await tokenA.balanceOf(owner.address)).to.equal(ownerBefore + fee);
      expect(await escrow.collectedFees(tokenAAddr)).to.equal(0n);
    });

    it("non-owner cannot toggle fee or withdraw", async function () {
      await expect(
        escrow.connect(attacker).setFeeEnabled(true)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");

      await expect(
        escrow.connect(attacker).withdrawFees(await tokenA.getAddress(), attacker.address)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  //  ⑦ Security  (P1)
  // ═══════════════════════════════════════════════════════════════════════════

  describe("⑦ Security (P1)", function () {

    // ── 7a. Fake signature rejection ─────────────────────────────────────────

    describe("Fake signature rejection (위조 서명 거부)", function () {
      it("wrong TEE signer key → reverts", async function () {
        const { makerOrderId, takerOrderId } = await depositBoth();
        const fakeSigner = ethers.Wallet.createRandom();

        const swap = await buildSwap({
          makerOrderId, takerOrderId, signer: fakeSigner,
        });

        await expect(
          escrow.connect(anyone).executeSwap(
            swap.swapId, swap.makerOrderId, swap.takerOrderId,
            swap.makerFillAmount, swap.takerFillAmount, swap.sig
          )
        ).to.be.revertedWith("DPE: invalid TEE signature");
      });

      it("tampered fill amount → reverts", async function () {
        const { makerOrderId, takerOrderId } = await depositBoth();

        // Sign for 100, submit 1
        const swap = await buildSwap({ makerOrderId, takerOrderId });

        await expect(
          escrow.connect(anyone).executeSwap(
            swap.swapId, swap.makerOrderId, swap.takerOrderId,
            ethers.parseEther("1"), // ← tampered
            swap.takerFillAmount,
            swap.sig
          )
        ).to.be.revertedWith("DPE: invalid TEE signature");
      });

      it("cross-chain replay → reverts", async function () {
        const { makerOrderId, takerOrderId } = await depositBoth();

        const wrongChainId = chainId + 1n;
        const structHash = ethers.solidityPackedKeccak256(
          ["uint256", "address", "bytes32", "bytes32", "bytes32", "uint256", "uint256"],
          [wrongChainId, escrowAddr, ethers.randomBytes(32), makerOrderId, takerOrderId, HUNDRED, FIFTY]
        );
        const badSig = await teeSigner.signMessage(ethers.getBytes(structHash));

        await expect(
          escrow.connect(anyone).executeSwap(
            ethers.randomBytes(32), makerOrderId, takerOrderId,
            HUNDRED, FIFTY, badSig
          )
        ).to.be.revertedWith("DPE: invalid TEE signature");
      });
    });

    // ── 7b. Double-execute / replay prevention (이중 실행 방지) ─────────────

    describe("Double-execute prevention (이중 실행 방지)", function () {
      it("same swapId cannot be executed twice", async function () {
        const { makerOrderId, takerOrderId } = await depositBoth(HUNDRED, FIFTY);
        const swap = await buildSwap({
          makerOrderId, takerOrderId,
          makerFillAmount: FIFTY, takerFillAmount: ethers.parseEther("25"),
        });

        await escrow.connect(anyone).executeSwap(
          swap.swapId, swap.makerOrderId, swap.takerOrderId,
          swap.makerFillAmount, swap.takerFillAmount, swap.sig
        );

        await expect(
          escrow.connect(anyone).executeSwap(
            swap.swapId, swap.makerOrderId, swap.takerOrderId,
            swap.makerFillAmount, swap.takerFillAmount, swap.sig
          )
        ).to.be.revertedWith("DPE: swap already executed");
      });

      it("zero fill amounts reverted", async function () {
        const { makerOrderId, takerOrderId } = await depositBoth();
        const swap = await buildSwap({
          makerOrderId, takerOrderId,
          makerFillAmount: 0n, takerFillAmount: 0n,
        });
        await expect(
          escrow.connect(anyone).executeSwap(
            swap.swapId, swap.makerOrderId, swap.takerOrderId,
            0n, 0n, swap.sig
          )
        ).to.be.revertedWith("DPE: zero fill");
      });
    });

    // ── 7c. Reentrancy prevention (재진입 공격 방어) ─────────────────────────

    describe("Reentrancy prevention (재진입 공격 방어)", function () {
      it("malicious token cannot re-enter executeSwap during transfer", async function () {
        // Deploy attacker token
        const AttackerF = await ethers.getContractFactory("ReentrancyAttacker");
        const malToken  = await AttackerF.deploy(escrowAddr);
        const malAddr   = await malToken.getAddress();

        // Mint + approve
        await malToken.mint(bob.address, MINT);
        await malToken.connect(bob).approve(escrowAddr, ethers.MaxUint256);

        // Deposit: Alice → Token A (normal), Bob → malicious token
        const makerOrderId = ethers.randomBytes(32);
        const takerOrderId = ethers.randomBytes(32);
        await escrow.connect(alice).deposit(makerOrderId, await tokenA.getAddress(), HUNDRED);
        await escrow.connect(bob).deposit(takerOrderId, malAddr, FIFTY);

        // Build valid swap
        const swapId = ethers.randomBytes(32);
        const swap   = await buildSwap({
          swapId, makerOrderId, takerOrderId,
          makerFillAmount: HUNDRED, takerFillAmount: FIFTY,
        });

        // Configure attacker: re-enter executeSwap on transfer()
        await malToken.configureExecuteAttack(
          swapId, makerOrderId, takerOrderId,
          HUNDRED, FIFTY, swap.sig
        );

        // Execute → malToken.transfer() tries to re-enter → ReentrancyGuard blocks
        await expect(
          escrow.connect(anyone).executeSwap(
            swap.swapId, swap.makerOrderId, swap.takerOrderId,
            swap.makerFillAmount, swap.takerFillAmount, swap.sig
          )
        ).to.be.revertedWithCustomError(escrow, "ReentrancyGuardReentrantCall");
      });

      it("malicious token cannot re-enter cancelOrder during refund", async function () {
        const AttackerF = await ethers.getContractFactory("ReentrancyAttacker");
        const malToken  = await AttackerF.deploy(escrowAddr);
        const malAddr   = await malToken.getAddress();

        await malToken.mint(alice.address, MINT);
        await malToken.connect(alice).approve(escrowAddr, ethers.MaxUint256);

        const orderId = ethers.randomBytes(32);
        await escrow.connect(alice).deposit(orderId, malAddr, HUNDRED);

        // Configure: re-enter cancelOrder on transfer()
        await malToken.configureCancelAttack(orderId);

        await expect(
          escrow.connect(alice).cancelOrder(orderId)
        ).to.be.revertedWithCustomError(escrow, "ReentrancyGuardReentrantCall");
      });
    });
  });
});
