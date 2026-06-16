#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细对比掩码评分的各项
"""

import qrcode
from qrcode.util import lost_point
from qrcode_generator import Masker, QRMatrix, DataEncoder, ReedSolomon, VersionSelector
from qrcode_generator import EC_LEVEL_L, QR_CAPACITY_TABLE


def build_our_matrix(data_bytes, version, ec_level, mask_num):
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
    return matrix


def main():
    data = b"Hello, World!"
    version = 1
    ec_level = EC_LEVEL_L
    
    print(f"测试: Hello World v1-L")
    print()
    
    # 标准库各掩码评分
    print("=" * 70)
    print("标准库评分 (util.lost_point)")
    print("=" * 70)
    print(f"{'掩码':>4}  {'总分':>6}  {'最佳标记':>8}")
    
    std_scores = []
    ec = qrcode.constants.ERROR_CORRECT_L
    for mask in range(8):
        qr = qrcode.QRCode(version=version, error_correction=ec, box_size=1, border=0, mask_pattern=mask)
        qr.add_data(data)
        qr.make(fit=False)
        mat = qr.get_matrix()
        bool_mat = [[bool(v) for v in row] for row in mat]
        score = lost_point(bool_mat)
        std_scores.append(score)
    
    std_best = min(range(8), key=lambda i: std_scores[i])
    for mask in range(8):
        marker = "  <-- 最佳" if mask == std_best else ""
        print(f"{mask:>4}  {std_scores[mask]:>6}{marker}")
    
    # 我们的评分
    print()
    print("=" * 70)
    print("我们的评分 (Masker.calculate_penalty)")
    print("=" * 70)
    print(f"{'掩码':>4}  {'总分':>6}  {'最佳标记':>8}")
    
    our_scores = []
    for mask in range(8):
        mat = build_our_matrix(data, version, ec_level, mask)
        score = Masker.calculate_penalty(mat)
        our_scores.append(score)
    
    our_best = min(range(8), key=lambda i: our_scores[i])
    for mask in range(8):
        marker = "  <-- 最佳" if mask == our_best else ""
        print(f"{mask:>4}  {our_scores[mask]:>6}{marker}")
    
    # 分数差异
    print()
    print("=" * 70)
    print("分数差异 (我们的 - 标准的)")
    print("=" * 70)
    print(f"{'掩码':>4}  {'差异':>6}")
    for mask in range(8):
        print(f"{mask:>4}  {our_scores[mask] - std_scores[mask]:>+6}")
    
    # 矩阵一致性
    print()
    print("=" * 70)
    print("矩阵一致性")
    print("=" * 70)
    for mask in range(8):
        our_mat = build_our_matrix(data, version, ec_level, mask)
        qr = qrcode.QRCode(version=version, error_correction=ec, box_size=1, border=0, mask_pattern=mask)
        qr.add_data(data)
        qr.make(fit=False)
        std_mat = [[bool(v) for v in row] for row in qr.get_matrix()]
        diffs = sum(1 for r in range(len(our_mat)) for c in range(len(our_mat[0])) if our_mat[r][c] != std_mat[r][c])
        print(f"  掩码 {mask}: {diffs} 个差异")


if __name__ == '__main__':
    main()
