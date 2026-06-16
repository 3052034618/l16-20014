#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细对比掩码评分
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_M,
    EC_LEVEL_NAMES, QR_CAPACITY_TABLE,
)


def get_our_full_scores(data_bytes, version, ec_level):
    """获取我们的各掩码详细评分"""
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
    
    all_results = []
    for mask_num in range(8):
        m = QRMatrix(version)
        m.place_function_patterns(ec_level, mask_num)
        m.place_data(final_bits)
        masked = Masker.apply_mask_temp(m, mask_num)
        eval_mat = [[False if v is None else v for v in row] for row in masked]
        
        # 分项计算
        n1 = Masker._calc_n1(eval_mat) if hasattr(Masker, '_calc_n1') else 0
        n2 = Masker._calc_n2(eval_mat) if hasattr(Masker, '_calc_n2') else 0
        n3 = Masker._calc_n3(eval_mat) if hasattr(Masker, '_calc_n3') else 0
        n4 = Masker._calc_n4(eval_mat) if hasattr(Masker, '_calc_n4') else 0
        
        total = Masker.calculate_penalty(eval_mat)
        
        all_results.append({
            'mask': mask_num,
            'total': total,
            'n1': n1, 'n2': n2, 'n3': n3, 'n4': n4,
            'matrix': eval_mat,
        })
    
    return all_results, final_bits


def get_std_best_mask(data_bytes, version, ec_level):
    """获取标准库的最佳掩码"""
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
    )
    qr.add_data(data_bytes)
    qr.make(fit=False)
    best = qr.best_mask_pattern()
    
    # 获取各掩码的矩阵
    matrices = []
    for mask in range(8):
        qr2 = qrcode.QRCode(
            version=version,
            error_correction=ec_map[ec_level],
            box_size=1,
            border=0,
            mask_pattern=mask,
        )
        qr2.add_data(data_bytes)
        qr2.make(fit=False)
        matrices.append(qr2.get_matrix())
    
    return best, matrices


def main():
    data = b"Hello, World!"
    version = 1
    ec_level = EC_LEVEL_L
    
    print(f"测试: Hello World v1-L")
    print(f"数据: {len(data)} 字节")
    
    our_results, _ = get_our_full_scores(data, version, ec_level)
    std_best, std_matrices = get_std_best_mask(data, version, ec_level)
    
    print(f"\n标准库最佳掩码: {std_best}")
    print(f"\n我们的评分:")
    print(f"  掩码  总分   N1    N2    N3    N4")
    for r in our_results:
        marker = "  <-- 最佳" if r['mask'] == min(range(8), key=lambda i: our_results[i]['total']) else ""
        print(f"    {r['mask']}  {r['total']:4d}  {r['n1']:4d}  {r['n2']:4d}  {r['n3']:4d}  {r['n4']:4d}{marker}")
    
    # 用我们的评分函数去评标准库的矩阵
    print(f"\n用我们的评分函数评标准库的矩阵:")
    print(f"  掩码  总分")
    std_scores = []
    for mask in range(8):
        mat = std_matrices[mask]
        # 转换为 list[list[bool]]
        bool_mat = [[bool(v) for v in row] for row in mat]
        score = Masker.calculate_penalty(bool_mat)
        std_scores.append(score)
    
    best_our_on_std = min(range(8), key=lambda i: std_scores[i])
    for mask in range(8):
        marker = "  <-- 最佳" if mask == best_our_on_std else ""
        marker2 = "  <-- 标准最佳" if mask == std_best else ""
        print(f"    {mask}  {std_scores[mask]:4d}{marker}{marker2}")
    
    # 检查矩阵是否一致
    print(f"\n矩阵一致性检查:")
    for mask in range(8):
        our_mat = our_results[mask]['matrix']
        std_mat = [[bool(v) for v in row] for row in std_matrices[mask]]
        diffs = sum(1 for r in range(len(our_mat)) for c in range(len(our_mat[0])) if our_mat[r][c] != std_mat[r][c])
        print(f"  掩码 {mask}: {diffs} 个差异")


if __name__ == '__main__':
    main()
