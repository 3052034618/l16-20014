#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本信息详细调试
"""

import qrcode
from qrcode_generator import (
    QRMatrix, EC_LEVEL_M, VERSION_INFO_GEN_POLY
)


def encode_version_info_our(version):
    """我们的版本信息编码"""
    v = version << 12
    gen = VERSION_INFO_GEN_POLY
    
    for i in range(5, -1, -1):
        if (v >> (i + 12)) & 1:
            v ^= gen << i
    
    return (version << 12) | (v & 0xFFF)


def get_std_version_info(version):
    """从标准库获取版本信息的18位"""
    ec = qrcode.constants.ERROR_CORRECT_M
    qr = qrcode.QRCode(
        version=version,
        error_correction=ec,
        box_size=1,
        border=0,
        mask_pattern=0,
    )
    qr.add_data(b"test")
    qr.make(fit=False)
    matrix = qr.get_matrix()
    s = len(matrix)
    
    bits_pos1 = []
    bits_pos2 = []
    
    # 位置1：右上角，行0-5，列 s-11 到 s-9
    for r in range(6):
        for c in range(s - 11, s - 8):
            bits_pos1.append(1 if matrix[r][c] else 0)
    
    # 位置2：左下角，列0-5，行 s-11 到 s-9
    for r in range(s - 11, s - 8):
        for c in range(6):
            bits_pos2.append(1 if matrix[r][c] else 0)
    
    return bits_pos1, bits_pos2, s


def main():
    version = 7
    
    # 我们的编码
    our_ver = encode_version_info_our(version)
    our_bits = [(our_ver >> i) & 1 for i in range(17, -1, -1)]
    print(f"我们的版本{version}编码: {our_ver:018b} (0x{our_ver:05x})")
    print(f"  位顺序 (MSB→LSB): {''.join(str(b) for b in our_bits)}")
    
    # 标准库的
    std_pos1, std_pos2, s = get_std_version_info(version)
    print(f"\n标准库版本{version}，大小 {s}x{s}")
    print(f"  位置1（右上，行优先）: {''.join(str(b) for b in std_pos1)}")
    print(f"  位置2（左下，行优先）: {''.join(str(b) for b in std_pos2)}")
    
    # 对比
    print(f"\n--- 对比 ---")
    print(f"我们的MSB→LSB:     {''.join(str(b) for b in our_bits)}")
    print(f"标准位置1行优先:   {''.join(str(b) for b in std_pos1)}")
    print(f"标准位置2行优先:   {''.join(str(b) for b in std_pos2)}")
    
    # 检查位置1和位置2是否相同（互为镜像？）
    if std_pos1 == std_pos2:
        print("\n位置1和位置2相同")
    elif std_pos1 == std_pos2[::-1]:
        print("\n位置1和位置2互为逆序")
    else:
        print("\n位置1和位置2不同")
        diffs = sum(1 for a, b in zip(std_pos1, std_pos2) if a != b)
        print(f"  差异位数: {diffs}")
    
    # 尝试不同的位顺序
    print(f"\n--- 尝试不同排列方式 ---")
    
    # 我们的：列优先的位置1 vs 标准的行优先的位置1
    # 我们的位置1是：列0-5，行s-11到s-8（列优先）
    # 让我们按列优先重新排列标准位置2的数据
    std_pos2_col_major = []
    for c in range(6):
        for r in range(s - 11, s - 8):
            matrix = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=0, mask_pattern=0)
            matrix.add_data(b"test")
            matrix.make(fit=False)
            m = matrix.get_matrix()
            std_pos2_col_major.append(1 if m[r][c] else 0)
    
    print(f"标准位置2列优先:   {''.join(str(b) for b in std_pos2_col_major)}")
    
    # 我们的位置2是：行0-5，列s-11到s-8（行优先）
    std_pos1_row_major = []
    for r in range(6):
        for c in range(s - 11, s - 8):
            matrix = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=0, mask_pattern=0)
            matrix.add_data(b"test")
            matrix.make(fit=False)
            m = matrix.get_matrix()
            std_pos1_row_major.append(1 if m[r][c] else 0)
    
    print(f"标准位置1行优先:   {''.join(str(b) for b in std_pos1_row_major)}")


if __name__ == '__main__':
    main()
