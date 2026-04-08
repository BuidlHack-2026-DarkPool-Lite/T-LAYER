import { useCallback, useMemo } from 'react';
import { ethers } from 'ethers';
import { config, TOKEN_ADDRESSES } from '../config';
import { ERC20_ABI, ESCROW_ABI } from '../abi';

/**
 * orderId (hex string from backend) → bytes32
 * 백엔드에서 uuid4().hex 형태로 오는 32자 hex → 0x prefix + zero-pad
 */
function toBytes32(orderId: string): string {
  const hex = orderId.startsWith('0x') ? orderId : `0x${orderId}`;
  return ethers.zeroPadValue(hex, 32);
}

export function useEscrow(signer: ethers.JsonRpcSigner | null, provider: ethers.BrowserProvider | null) {
  const escrowContract = useMemo(() => {
    if (!signer || !config.ESCROW_ADDRESS) return null;
    return new ethers.Contract(config.ESCROW_ADDRESS, ESCROW_ABI, signer);
  }, [signer]);

  /** ERC20 approve — Escrow 컨트랙트에 토큰 사용 승인 */
  const approveToken = useCallback(
    async (tokenAddress: string, amount: bigint) => {
      if (!signer) throw new Error('Wallet not connected');
      const token = new ethers.Contract(tokenAddress, ERC20_ABI, signer);
      const tx = await token.approve(config.ESCROW_ADDRESS, amount);
      return tx.wait(1);
    },
    [signer],
  );

  /** Escrow deposit — 토큰 예치 */
  const deposit = useCallback(
    async (orderId: string, tokenAddress: string, amount: bigint) => {
      if (!escrowContract) throw new Error('Escrow contract not configured');
      const tx = await escrowContract.deposit(toBytes32(orderId), tokenAddress, amount);
      return tx.wait(1);
    },
    [escrowContract],
  );

  /** 주문 취소 — 미체결 잔량 환불 */
  const cancelOrder = useCallback(
    async (orderId: string) => {
      if (!escrowContract) throw new Error('Escrow contract not configured');
      const tx = await escrowContract.cancelOrder(toBytes32(orderId));
      return tx.wait(1);
    },
    [escrowContract],
  );

  /** 온체인 주문 상태 조회 */
  const getOrderState = useCallback(
    async (orderId: string) => {
      if (!escrowContract) return null;
      const [trader, token, totalAmount, filledAmount, active] = await escrowContract.orders(toBytes32(orderId));
      return { trader, token, totalAmount, filledAmount, active };
    },
    [escrowContract],
  );

  /** 미체결 잔량 조회 */
  const getOrderRemaining = useCallback(
    async (orderId: string): Promise<bigint> => {
      if (!escrowContract) return 0n;
      return escrowContract.getOrderRemaining(toBytes32(orderId));
    },
    [escrowContract],
  );

  /** ERC20 잔고 조회 */
  const getTokenBalance = useCallback(
    async (tokenSymbol: string, walletAddress: string): Promise<string> => {
      if (!provider) return '0';
      const tokenAddress = TOKEN_ADDRESSES[tokenSymbol];
      if (!tokenAddress) return '0';

      try {
        const token = new ethers.Contract(tokenAddress, ERC20_ABI, provider);
        const [balance, decimals] = await Promise.all([
          token.balanceOf(walletAddress),
          token.decimals(),
        ]);
        return ethers.formatUnits(balance, decimals);
      } catch {
        return '0';
      }
    },
    [provider],
  );

  return {
    approveToken,
    deposit,
    cancelOrder,
    getOrderState,
    getOrderRemaining,
    getTokenBalance,
  };
}
