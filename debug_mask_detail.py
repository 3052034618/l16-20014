#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细调试掩码评分差异 - v1-M 10字节
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    QR_CAPACITY_TABLE, EC_LEVEL_M,
)

# 测试数据
data = b"A" * 10
version = 1
ec_level = EC_LEVEL_M

# ========== 标准库 ==========
qr = qrcode.QRCode(
    version=version,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=1,
    border=0,
)
qr.add_data(data, optimize=0)
qr.make(fit=False)

print("=== 标准库信息 ===")
print(f"data_cache 长度: {len(qr.data_cache)}")
print(f"data_cache 前30字节: {''.join(f'{x:02x}' for x in qr.data_cache[:30])}")

# 标准库各掩码评分
print("\n标准库各掩码评分（test模式）:")
std_scores = []
for i in range(8):
    qr.makeImpl(True, i)
    score = qrcode.util.lost_point(qr.modules)
    std_scores.append(score)
    print(f"  掩码 {i}: {score}")

print(f"标准库最佳掩码: {std_scores.index(min(std_scores))} (分数={min(std_scores)})")

# ========== 我们的实现 ==========
print("\n=== 我们的实现 ===")

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

# 转成字节看看
final_bytes = []
for i in range(0, len(final_bits) - rem, 8):
    byte = 0
    for j in range(8):
        byte = (byte << 1) | final_bits[i + j]
    final_bytes.append(byte)

print(f"最终字节数: {len(final_bytes)}")
print(f"最终字节前30个: {''.join(f'{x:02x}' for x in final_bytes[:30])}")

# 数据是否一致
print(f"\ndata_cache 和我们的 final_bytes 是否一致: {list(qr.data_cache) == final_bytes}")
if list(qr.data_cache) != final_bytes:
    # 找出第一个不同的位置
    for i in range(min(len(qr.data_cache), len(final_bytes))):
        if qr.data_cache[i] != final_bytes[i]:
            print(f"第一个不同位置: {i}, 标准={qr.data_cache[i]:02x}, 我们={final_bytes[i]:02x}")
            break
    if len(qr.data_cache) != len(final_bytes):
        print(f"长度不同: 标准={len(qr.data_cache)}, 我们={len(final_bytes)}")

# 我们的各掩码评分（test模式）
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

# 对比总分差异
print("\n=== 评分差异对比 ===")
for i in range(8):
    diff = our_scores[i] - std_scores[i]
    print(f"  掩码 {i}: 标准={std_scores[i]}, 我们={our_scores[i]}, 差异={diff:+d}")

# 详细对比单个掩码的各项评分
print("\n=== 掩码 0 各项评分对比 ===")
# 标准库掩码0 test模式矩阵
qr.makeImpl(True, 0)
std_mat = qr.modules
std_n1 = qrcode.util._lost_point_level1(std_mat, len(std_mat))
std_n2 = qrcode.util._lost_point_level2(std_mat, len(std_mat))
std_n3 = qrcode.util._lost_point_level3(std_mat, len(std_mat))
std_n4 = qrcode.util._lost_point_level4(std_mat, len(std_mat))
print(f"标准库: N1={std_n1}, N2={std_n2}, N3={std_n3}, N4={std_n4}, 总={std_n1+std_n2+std_n3+std_n4}")

# 我们的掩码0 test模式矩阵
temp = QRMatrix(version)
temp.place_function_patterns(ec_level, 0, test=True)
temp.place_data(final_bits)
masked = Masker.apply_mask_temp(temp, 0)
our_mat = [[False if v is None else v for v in row] for row in masked]

# 手动计算各项
def calc_n1(modules, n):
    penalty = 0
    container = [0] * (n + 1)
    for row in range(n):
        prev = modules[row][0]
        length = 0
        for col in range(n):
            if modules[row][col] == prev:
                length += 1
            else:
                if length >= 5:
                    container[length] += 1
                length = 1
                prev = modules[row][col]
        if length >= 5:
            container[length] += 1
    for col in range(n):
        prev = modules[0][col]
        length = 0
        for row in range(n):
            if modules[row][col] == prev:
                length += 1
            else:
                if length >= 5:
                    container[length] += 1
                length = 1
                prev = modules[row][col]
        if length >= 5:
            container[length] += 1
    penalty = sum(container[l] * (l - 2) for l in range(5, n + 1))
    return penalty

def calc_n2(modules, n):
    penalty = 0
    for r in range(n - 1):
        for c in range(n - 1):
            v = modules[r][c]
            if v == modules[r][c+1] == modules[r+1][c] == modules[r+1][c+1]:
                penalty += 3
    return penalty

def calc_n3(modules, n):
    penalty = 0
    for r in range(n):
        row = [modules[r][c] for c in range(n)]
        penalty += Masker._check_finder_pattern_line(row) * 40
    for c in range(n):
        col = [modules[r][c] for r in range(n)]
        penalty += Masker._check_finder_pattern_line(col) * 40
    return penalty

def calc_n4(modules, n):
    dark = sum(1 for r in range(n) for c in range(n) if modules[r][c])
    percent = dark / (n * n) * 100
    k = abs(percent - 50) / 5
    return int(k) * 10

our_n1 = calc_n1(our_mat, len(our_mat))
our_n2 = calc_n2(our_mat, len(our_mat))
our_n3 = calc_n3(our_mat, len(our_mat))
our_n4 = calc_n4(our_mat, len(our_mat))
print(f"我们的: N1={our_n1}, N2={our_n2}, N3={our_n3}, N4={our_n4}, 总={our_n1+our_n2+our_n3+our_n4}")

print(f"\n差异: N1={our_n1-std_n1:+d}, N2={our_n2-std_n2:+d}, N3={our_n3-std_n3:+d}, N4={our_n4-std_n4:+d}")

# 检查矩阵是否完全一致
print("\n=== 矩阵一致性检查 ===")
size = len(std_mat)
diff_count = 0
first_diff = None
for r in range(size):
    for c in range(size):
        sv = std_mat[r][c]
        ov = our_mat[r][c]
        if sv != ov:
            diff_count += 1
            if first_diff is None:
                first_diff = (r, c, sv, ov)

print(f"差异模块数: {diff_count}")
if first_diff:
    print(f"第一个差异: ({first_diff[0]}, {first_diff[1]}) 标准={first_diff[2]}, 我们={first_diff[3]}")
