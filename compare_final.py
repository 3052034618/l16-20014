#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终对比 - 版本1，字节数据，掩码0
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
    qr.add_data(data_bytes)
    qr.make(fit=True)
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
    data = bytes([0x12, 0x34, 0x56, 0x78])
    version = 1
    ec_level = EC_LEVEL_L
    mask_num = 0
    
    print("=" * 70)
    print(f"对比：{len(data)}字节, 版本{version}-{EC_LEVEL_NAMES[ec_level]}, 掩码{mask_num}")
    print("=" * 70)
    
    std_matrix = get_std_matrix(data, version, ec_level, mask_pattern=mask_num)
    our_matrix, is_func = get_our_matrix(data, version, ec_level, mask_num)
    s = len(std_matrix)
    
    print(f"标准库大小: {s}x{s}")
    print(f"我们的大小: {len(our_matrix)}x{len(our_matrix)}")
    
    # 数据模块坐标
    data_coords = list_data_modules_in_order(is_func, s)
    print(f"\n数据模块数: {len(data_coords)}")
    
    # 总差异
    total_diff = 0
    for r in range(s):
        for c in range(s):
            if std_matrix[r][c] != our_matrix[r][c]:
                total_diff += 1
    print(f"总差异数: {total_diff}")
    
    # 数据区域差异
    data_diff = 0
    first_data_diff = -1
    for i, (r, c) in enumerate(data_coords):
        if std_matrix[r][c] != our_matrix[r][c]:
            data_diff += 1
            if first_data_diff < 0:
                first_data_diff = i
    
    print(f"数据区域差异: {data_diff}")
    if first_data_diff >= 0:
        print(f"第一个数据差异在第 {first_data_diff} 位")
        r, c = data_coords[first_data_diff]
        print(f"  位置: ({r}, {c})")
        print(f"  标准: {1 if std_matrix[r][c] else 0}")
        print(f"  我们: {1 if our_matrix[r][c] else 0}")
    
    # 逐字节对比
    print(f"\n逐字节对比（去掩码后）：")
    all_bits = []
    for r, c in data_coords:
        sv = std_matrix[r][c]
        ov = our_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            sv = not sv
            ov = not ov
        all_bits.append((1 if sv else 0, 1 if ov else 0))
    
    std_bytes = []
    our_bytes = []
    for i in range(0, len(all_bits) - 7, 8):
        sb = 0
        ob = 0
        for j in range(8):
            sb = (sb << 1) | all_bits[i + j][0]
            ob = (ob << 1) | all_bits[i + j][1]
        std_bytes.append(sb)
        our_bytes.append(ob)
    
    print(f"  标准库字节数: {len(std_bytes)}")
    print(f"  我们的字节数: {len(our_bytes)}")
    
    diff_bytes = 0
    first_diff_byte = -1
    for i in range(min(len(std_bytes), len(our_bytes))):
        if std_bytes[i] != our_bytes[i]:
            diff_bytes += 1
            if first_diff_byte < 0:
                first_diff_byte = i
    
    print(f"  差异字节数: {diff_bytes}")
    if first_diff_byte >= 0:
        print(f"  第一个差异字节: {first_diff_byte}")
        print(f"    标准: 0x{std_bytes[first_diff_byte]:02x}")
        print(f"    我们: 0x{our_bytes[first_diff_byte]:02x}")
        
        # 打印前后几个字节
        print(f"\n  第{first_diff_byte-2}到{first_diff_byte+5}字节：")
        print(f"    索引: ", end="")
        for i in range(max(0, first_diff_byte-2), min(len(std_bytes), first_diff_byte+5)):
            print(f"{i:4d}", end="")
        print()
        print(f"    标准: ", end="")
        for i in range(max(0, first_diff_byte-2), min(len(std_bytes), first_diff_byte+5)):
            print(f" {std_bytes[i]:02x}", end="")
        print()
        print(f"    我们: ", end="")
        for i in range(max(0, first_diff_byte-2), min(len(our_bytes), first_diff_byte+5)):
            print(f" {our_bytes[i]:02x}", end="")
        print()


if __name__ == '__main__':
    main()
