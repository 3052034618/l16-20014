#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用字节数据对比，确保两边都用字节模式
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_NAMES, QR_CAPACITY_TABLE
)


def get_std_matrix(data_bytes, version, ec_level, mask_pattern=0):
    ec_map = {
        0: qrcode.constants.ERROR_CORRECT_L,
        1: qrcode.constants.ERROR_CORRECT_M,
        2: qrcode.constants.ERROR_CORRECT_Q,
        3: qrcode.constants.ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(
        version=version,
        error_correction=ec_map[ec_level],
        box_size=1,
        border=0,
        mask_pattern=mask_pattern,
    )
    # 直接添加字节数据
    qr.add_data(data_bytes)
    qr.make(fit=True)
    return qr.get_matrix()


def get_our_matrix(data_bytes, version, ec_level, mask_num=0):
    # 手动构建字节模式的比特流
    bits = [0, 1, 0, 0]  # 字节模式 0100
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
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, mask_num)
    m.place_data(final_bits)
    Masker.apply_mask(m, mask_num)
    
    matrix = [[False if v is None else v for v in row] for row in m.modules]
    return matrix, final_bits, m.is_function


def list_data_modules_in_order(is_func, size):
    coords = []
    col_pair = 0
    while True:
        right_col = size - 1 - col_pair * 2
        left_col = right_col - 1
        if left_col == 6:
            left_col = 5
        if right_col <= 0:
            break
        
        upward = (col_pair % 2 == 0)
        rows = range(size - 1, -1, -1) if upward else range(size)
        
        for row in rows:
            for c in [right_col, left_col]:
                if not is_func[row][c]:
                    coords.append((row, c))
        col_pair += 1
    return coords


def main():
    # 用字节数据
    data = bytes([0x12, 0x34, 0x56, 0x78])
    version = 1
    ec_level = EC_LEVEL_L
    mask_num = 0
    
    print("=" * 70)
    print(f"对比测试：{len(data)}字节数据, 版本{version}-{EC_LEVEL_NAMES[ec_level]}, 掩码{mask_num}")
    print("=" * 70)
    
    # 标准库
    std_matrix = get_std_matrix(data, version, ec_level, mask_pattern=mask_num)
    s = len(std_matrix)
    print(f"标准库矩阵大小: {s}x{s}")
    
    # 我们的
    our_matrix, our_bits, is_func = get_our_matrix(data, version, ec_level, mask_num)
    print(f"我们的矩阵大小: {len(our_matrix)}x{len(our_matrix)}")
    
    # 统计总差异
    diff_count = 0
    func_diff = 0
    data_diff = 0
    for r in range(s):
        for c in range(s):
            if std_matrix[r][c] != our_matrix[r][c]:
                diff_count += 1
                if is_func[r][c]:
                    func_diff += 1
                else:
                    data_diff += 1
    
    print(f"\n总差异数: {diff_count}")
    print(f"  功能图案差异: {func_diff}")
    print(f"  数据区域差异: {data_diff}")
    
    # 数据模块坐标
    data_coords = list_data_modules_in_order(is_func, s)
    print(f"\n数据模块总数: {len(data_coords)}")
    
    # 前50位数据对比（去掩码后）
    print(f"\n前50位数据对比（去掩码后）：")
    std_unmasked = []
    our_unmasked = []
    for r, c in data_coords[:50]:
        sv = std_matrix[r][c]
        ov = our_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            sv = not sv
            ov = not ov
        std_unmasked.append(1 if sv else 0)
        our_unmasked.append(1 if ov else 0)
    
    print(f"  标准库: {''.join(str(b) for b in std_unmasked)}")
    print(f"  我们的: {''.join(str(b) for b in our_unmasked)}")
    
    # 期望的
    expected = [0, 1, 0, 0]  # 字节模式
    byte_len = len(data)
    cc_bits = 8 if version <= 9 else 16
    expected.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
    for byte in data:
        expected.extend([int(b) for b in format(byte, '08b')])
    print(f"  期望  : {''.join(str(b) for b in expected[:50])}")
    
    # 找第一个差异
    first_diff = -1
    for i in range(min(len(std_unmasked), len(our_unmasked))):
        if std_unmasked[i] != our_unmasked[i]:
            first_diff = i
            break
    if first_diff >= 0:
        print(f"\n第一个数据差异在第 {first_diff} 位")
        r, c = data_coords[first_diff]
        print(f"  位置: ({r}, {c})")
        print(f"  标准: {std_unmasked[first_diff]}")
        print(f"  我们: {our_unmasked[first_diff]}")
    else:
        print(f"\n前50位数据完全一致！✓")
    
    # 检查所有数据位
    all_same = True
    for i, (r, c) in enumerate(data_coords):
        sv = std_matrix[r][c]
        ov = our_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            sv = not sv
            ov = not ov
        if sv != ov:
            all_same = False
            print(f"\n第一个差异在第 {i} 位，位置 ({r}, {c})")
            break
    
    if all_same:
        print(f"\n所有数据位完全一致！✓✓✓")


if __name__ == '__main__':
    main()
