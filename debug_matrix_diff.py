#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比中文v3-M掩码0的矩阵差异
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
mask_num = 0

# 标准库 - test模式
qr = qrcode.QRCode(
    version=version,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=1,
    border=0,
)
qr.add_data(data_text, optimize=0)
qr.makeImpl(True, mask_num)
std_mat = qr.modules

# 我们的 - test模式
data_bytes = data_text.encode('utf-8')
bits = [0, 1, 0, 0]
byte_len = len(data_bytes)
cc_bits = 8 if version <= 9 else 16
bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
for byte in data_bytes:
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

temp = QRMatrix(version)
temp.place_function_patterns(ec_level, mask_num, test=True)
temp.place_data(final_bits)
masked = Masker.apply_mask_temp(temp, mask_num)
our_mat = [[False if v is None else v for v in row] for row in masked]

# 对比
size = len(std_mat)
print(f"矩阵大小: {size}x{size}")

diff_count = 0
diffs = []
for r in range(size):
    for c in range(size):
        sv = std_mat[r][c]
        ov = our_mat[r][c]
        if sv != ov:
            diff_count += 1
            if len(diffs) < 30:
                diffs.append((r, c, sv, ov))

print(f"差异模块数: {diff_count}")
print(f"前30个差异:")
for r, c, sv, ov in diffs:
    print(f"  ({r:2d}, {c:2d}): 标准={sv}, 我们={ov}")

# 检查功能图案区域
print("\n=== 检查定位图案 ===")
# 左上角
for r in range(7):
    for c in range(7):
        sv = std_mat[r][c]
        ov = our_mat[r][c]
        if sv != ov:
            print(f"  左上角 ({r},{c}): 标准={sv}, 我们={ov}")

# 右上角
for r in range(7):
    for c in range(size-7, size):
        sv = std_mat[r][c]
        ov = our_mat[r][c]
        if sv != ov:
            print(f"  右上角 ({r},{c}): 标准={sv}, 我们={ov}")

# 左下角
for r in range(size-7, size):
    for c in range(7):
        sv = std_mat[r][c]
        ov = our_mat[r][c]
        if sv != ov:
            print(f"  左下角 ({r},{c}): 标准={sv}, 我们={ov}")

# 定时图案
print("\n=== 检查定时图案 ===")
# 行6
diff_timing = 0
for c in range(size):
    sv = std_mat[6][c]
    ov = our_mat[6][c]
    if sv != ov:
        diff_timing += 1
        if diff_timing <= 10:
            print(f"  行6 列{c}: 标准={sv}, 我们={ov}")
print(f"  行定时图案差异数: {diff_timing}")

# 列6
diff_timing_col = 0
for r in range(size):
    sv = std_mat[r][6]
    ov = our_mat[r][6]
    if sv != ov:
        diff_timing_col += 1
print(f"  列定时图案差异数: {diff_timing_col}")

# 格式信息
print("\n=== 检查格式信息 ===")
# 列8
fmt_diff_col8 = 0
for r in range(size):
    if r == 6:
        continue
    sv = std_mat[r][8]
    ov = our_mat[r][8]
    if sv != ov:
        fmt_diff_col8 += 1
        if fmt_diff_col8 <= 10:
            print(f"  列8 行{r}: 标准={sv}, 我们={ov}")
print(f"  列8格式信息差异数: {fmt_diff_col8}")

# 行8
fmt_diff_row8 = 0
for c in range(size):
    if c == 6:
        continue
    sv = std_mat[8][c]
    ov = our_mat[8][c]
    if sv != ov:
        fmt_diff_row8 += 1
        if fmt_diff_row8 <= 10:
            print(f"  行8 列{c}: 标准={sv}, 我们={ov}")
print(f"  行8格式信息差异数: {fmt_diff_row8}")

# 对齐图案
print("\n=== 检查对齐图案 ===")
# 版本3的对齐图案位置应该是 (6, 6)？不对，版本3有一个对齐图案
# 让我看看位置
from qrcode_generator import ALIGNMENT_PATTERN_POSITIONS
positions = ALIGNMENT_PATTERN_POSITIONS[version]
print(f"  版本{version}对齐图案位置: {positions}")

for r_pos in positions:
    for c_pos in positions:
        # 跳过和定位图案重叠的位置
        if (r_pos == 6 and c_pos == 6):
            continue
        if (r_pos == 6 and c_pos == size - 7) or (r_pos == size - 7 and c_pos == 6):
            continue
        # 检查这个对齐图案
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r = r_pos + dr
                c = c_pos + dc
                if 0 <= r < size and 0 <= c < size:
                    sv = std_mat[r][c]
                    ov = our_mat[r][c]
                    if sv != ov:
                        print(f"  对齐图案 ({r},{c}): 标准={sv}, 我们={ov}")
