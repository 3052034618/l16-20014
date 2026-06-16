#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本7对比测试
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_M, EC_LEVEL_NAMES, QR_CAPACITY_TABLE
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
    qr.add_data(data_bytes)
    qr.make(fit=False)
    return qr.get_matrix()


def get_our_matrix(data_bytes, version, ec_level, mask_num=0):
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
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, mask_num)
    m.place_data(final_bits)
    Masker.apply_mask(m, mask_num)
    
    matrix = [[False if v is None else v for v in row] for row in m.modules]
    return matrix, m.is_function


def list_data_modules_in_order(is_func, size):
    coords = []
    right_col = size - 1
    col_pair = 0
    
    while right_col >= 0:
        left_col = right_col - 1
        if left_col == 6:
            left_col = 5
        
        upward = (col_pair % 2 == 0)
        rows = range(size - 1, -1, -1) if upward else range(size)
        
        for row in rows:
            for c in [right_col, left_col]:
                if c >= 0 and not is_func[row][c]:
                    coords.append((row, c))
        
        right_col = left_col - 1
        if right_col == 6:
            right_col = 5
        col_pair += 1
    
    return coords


def main():
    # 50字节数据
    data = bytes(range(50))
    version = 7
    ec_level = EC_LEVEL_M
    mask_num = 0
    
    print(f"版本 {version}-{EC_LEVEL_NAMES[ec_level]}, 掩码 {mask_num}")
    print(f"数据: {len(data)} 字节")
    
    std_matrix = get_std_matrix(data, version, ec_level, mask_pattern=mask_num)
    our_matrix, is_func = get_our_matrix(data, version, ec_level, mask_num)
    s = len(std_matrix)
    
    print(f"标准库大小: {s}x{s}")
    print(f"我们的大小: {len(our_matrix)}x{len(our_matrix)}")
    
    # 数据模块数
    data_coords = list_data_modules_in_order(is_func, s)
    print(f"数据模块数: {len(data_coords)}")
    
    # 总差异
    total_diff = 0
    func_diff = 0
    data_diff = 0
    for r in range(s):
        for c in range(s):
            if std_matrix[r][c] != our_matrix[r][c]:
                total_diff += 1
                if is_func[r][c]:
                    func_diff += 1
                else:
                    data_diff += 1
    
    print(f"\n总差异: {total_diff}")
    print(f"  功能图案差异: {func_diff}")
    print(f"  数据区域差异: {data_diff}")
    
    # 检查版本信息区域
    print(f"\n--- 版本信息区域检查 ---")
    print(f"版本7，矩阵大小 {s}x{s}")
    
    # 版本信息位置1：右上角，行0-5，列s-11到s-9（3行x6列）
    print(f"\n位置1（右上角，行0-5，列{s-11}到{s-9}）:")
    print("       ", end="")
    for c in range(s - 11, s - 8):
        print(f" 列{c}", end="")
    print()
    for r in range(6):
        print(f"  行{r}: ", end="")
        for c in range(s - 11, s - 8):
            sv = '1' if std_matrix[r][c] else '0'
            ov = '1' if our_matrix[r][c] else '0'
            match = ' ' if sv == ov else 'X'
            print(f" {sv}/{ov}{match}", end="")
        print()
    
    # 版本信息位置2：左下角，列0-5，行s-11到s-9
    print(f"\n位置2（左下角，列0-5，行{s-11}到{s-9}）:")
    print("       ", end="")
    for c in range(6):
        print(f" 列{c}", end="")
    print()
    for r in range(s - 11, s - 8):
        print(f"  行{r}: ", end="")
        for c in range(6):
            sv = '1' if std_matrix[r][c] else '0'
            ov = '1' if our_matrix[r][c] else '0'
            match = ' ' if sv == ov else 'X'
            print(f" {sv}/{ov}{match}", end="")
        print()
    
    # 数据区域第一个差异
    if data_diff > 0:
        first_data_diff = -1
        for i, (r, c) in enumerate(data_coords):
            if std_matrix[r][c] != our_matrix[r][c]:
                first_data_diff = i
                break
        if first_data_diff >= 0:
            r, c = data_coords[first_data_diff]
            print(f"\n第一个数据差异在第 {first_data_diff} 位, 位置 ({r}, {c})")


if __name__ == '__main__':
    main()
