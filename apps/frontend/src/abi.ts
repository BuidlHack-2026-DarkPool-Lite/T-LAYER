/** 컨트랙트 ABI — DarkPoolEscrow는 단일 진실원의 const TS export, ERC20은 viem 표준. */

import { erc20Abi } from 'viem';

// tools/sync-abi.mjs가 hardhat 컴파일 후 생성하는 const-narrowed TS 파일.
// JSON import는 string literal을 widening해서 wagmi v3 functionName 추론을
// 깨므로 frontend는 .json 대신 .ts 쪽을 import한다 (engine은 .json 사용).
import { DARKPOOLESCROW_ABI } from '../../../packages/contracts-abi/DarkPoolEscrow';

/** DarkPoolEscrow 전체 ABI. */
export const ESCROW_ABI = DARKPOOLESCROW_ABI;

/** ERC20 표준 ABI — viem 제공. */
export const ERC20_ABI = erc20Abi;
