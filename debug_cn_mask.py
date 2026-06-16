#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试中文v3-M掩码不一致的问题
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    QR_CAPACITY_TABLE, EC_LEVEL_M,
)

# 测试数据
data_text = "你好世界测试"
version = 3
ec_level = EC_LEVEL_M

# 标准库
qr = qrcode.QRCode(
    version=version,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=1,
    border=0,
)
qr.add_data(data_text, optimize=0)
qr.make(fit=False)

print("=== 标准库 ===")
print(f"data_list: {[(item.mode, len(item.data)) for item in qr.data_list]}")
print(f"data_cache 长度: {len(qr.data_cache)}")

# 标准库各掩码评分
print("\n标准库各掩码评分（test模式）:")
std_scores = []
for i in range(8):
    qr.makeImpl(True, i)
    score = qrcode.util.lost_point(qr.modules)
    std_scores.append(score)
    print(f"  掩码 {i}: {score}")

print(f"标准库最佳掩码: {std_scores.index(min(std_scores))} (分数={min(std_scores)})")

# 我们的实现
print("\n=== 我们的实现 ===")

data_bytes = data_text.encode('utf-8')
print(f"数据字节数: {len(data_bytes)}")

bits = [0, 1, 0, 0]
byte_len = len(data_bytes)
cc_bits = 8 if version <= 9 else 16
bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
for byte in data_bytes:
    bits.extend([int(b) for b in format(byte, '08b')])

cap = QR_CAPACITY_TABLE[ec_level][version]
total_bits = cap['total_data_codewords'] * 8
print(f"总数据位: {total_bits}")
bits = DataEncoder.pad_bits(bits, total_bits)
data_cw = DataEncoder.bits_to_bytes(bits)
print(f"数据码字: {len(data_cw)}")

blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec_level, version)
print(f"块数: {len(blocks)}, 每块EC码: {ec_per}")
ec_blocks = [ReedSolomon.encode(b, ec_per) for b in blocks]
interleaved_data = DataEncoder.interleave(blocks)
interleaved_ec = DataEncoder.interleave(ec_blocks)
rem = VersionSelector.get_remainder_bits(version)
final_bits = DataEncoder.build_final_bitstream(interleaved_data, interleaved_ec, rem)

# 转字节
final_bytes = []
for i in range(0, len(final_bits) - rem, 8):
    byte = 0
    for j in range(8):
        byte = (byte << 1) | final_bits[i + j]
    final_bytes.append(byte)

print(f"最终字节数: {len(final_bytes)}")
print(f"前20字节: {''.join(f'{x:02x}' for x in final_bytes[:20])}")

# 数据是否一致
print(f"\ndata_cache 与 final_bytes 一致: {list(qr.data_cache) == final_bytes}")
if list(qr.data_cache) != final_bytes:
    print(f"标准库前20字节: {''.join(f'{x:02x}' for x in qr.data_cache[:20])}")

# 我们的评分
print("\n我们的各掩码评分（test模式）:")
our_scores = []
for mask_num in range(8):
    temp = QRMatrix(version)
    temp.place_function_patterns(ec_level, mask_num, test=True)
    temp.place_data(final_bits)
    masked = Masker.apply_mask_temp(temp, mask_num)
    eval_mat = [[False if v is None else v for v in row] for row in masked]
    penalty = Masker.calculate_penalty(eval_mat)
    our_scores.append(penalty)
    print(f"  掩码 {mask_num}: {penalty}")

print(f"我们的最佳掩码: {our_scores.index(min(our_scores))} (分数={min(our_scores)})")

# 差异对比
print("\n=== 评分差异 ===")
for i in range(8):
    diff = our_scores[i] - std_scores[i]
    print(f"  掩码 {i}: 标准={std_scores[i]}, 我们={our_scores[i]}, 差={diff:+d}")
