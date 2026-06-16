#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试 v1-L 10字节 的掩码评分差异
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    QR_CAPACITY_TABLE, EC_LEVEL_L, EC_LEVEL_M,
)

# 测试数据
data = b"A" * 10
version = 1
ec_level = EC_LEVEL_M  # 调试不一致的 v1-M 情况

# 标准库
qr = qrcode.QRCode(
    version=version,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=1,
    border=0,
)
qr.add_data(data)
qr.make(fit=False)

print("标准库各掩码评分:")
for i in range(8):
    mat = qr.get_matrix()
    size = len(mat)
    # 标准库的 best_mask_pattern 会调用 makeImpl(True, i)
    # 但我们很难直接获取各掩码的评分
    pass

print(f"标准库最佳掩码: {qr.best_mask_pattern()}")

# 我们的评分
bits = [0, 1, 0, 0]
byte_len = len(data)
cc_bits = 8 if version <= 9 else 16
bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
for byte in data:
    bits.extend([int(b) for b in format(byte, '08b')])

cap = QR_CAPACITY_TABLE[ec_level][version]
total_bits = cap['total_data_codewords'] * 8
bits = DataEncoder.pad_bits(bits, total_bits)
data_cw = DataEncoder.bits_to_bytes(bits)
blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec_level, version)
ec_blocks = [ReedSolomon.encode(b, ec_per) for b in blocks]
interleaved_data = DataEncoder.interleave(blocks)
interleaved_ec = DataEncoder.interleave(ec_blocks)
rem = VersionSelector.get_remainder_bits(version)
final_bits = DataEncoder.build_final_bitstream(interleaved_data, interleaved_ec, rem)

print()
print("我们的各掩码评分（test模式）:")
scores = []
for mask_num in range(8):
    temp = QRMatrix(version)
    temp.place_function_patterns(ec_level, mask_num, test=True)
    temp.place_data(final_bits)
    masked = Masker.apply_mask_temp(temp, mask_num)
    eval_mat = [[False if v is None else v for v in row] for row in masked]
    penalty = Masker.calculate_penalty(eval_mat)
    scores.append(penalty)
    print(f"  掩码 {mask_num}: {penalty}")

print(f"我们的最佳掩码: {scores.index(min(scores))} (分数={min(scores)})")
print(f"  所有分数: {scores}")

# 也测试非test模式
print()
print("我们的各掩码评分（非test模式）:")
scores_no_test = []
for mask_num in range(8):
    temp = QRMatrix(version)
    temp.place_function_patterns(ec_level, mask_num, test=False)
    temp.place_data(final_bits)
    masked = Masker.apply_mask_temp(temp, mask_num)
    eval_mat = [[False if v is None else v for v in row] for row in masked]
    penalty = Masker.calculate_penalty(eval_mat)
    scores_no_test.append(penalty)
    print(f"  掩码 {mask_num}: {penalty}")

print(f"非test最佳掩码: {scores_no_test.index(min(scores_no_test))} (分数={min(scores_no_test)})")
