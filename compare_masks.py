#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比掩码评分和选择
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H,
    EC_LEVEL_NAMES, QR_CAPACITY_TABLE,
)


def get_our_mask_scores(data_bytes, version, ec_level):
    """获取我们的各掩码评分"""
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
    
    scores = []
    for mask_num in range(8):
        m = QRMatrix(version)
        m.place_function_patterns(ec_level, mask_num)
        m.place_data(final_bits)
        masked = Masker.apply_mask_temp(m, mask_num)
        eval_mat = [[False if v is None else v for v in row] for row in masked]
        penalty = Masker.calculate_penalty(eval_mat)
        scores.append(penalty)
    
    best_mask = min(range(8), key=lambda i: scores[i])
    return scores, best_mask, final_bits


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
    
    # 标准库的最佳掩码
    best_mask = qr.mask_pattern
    return best_mask, qr


def test_case(name, data_bytes, version, ec_level):
    """测试一个用例"""
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"  版本 {version}-{EC_LEVEL_NAMES[ec_level]}, 数据 {len(data_bytes)} 字节")
    
    our_scores, our_best, _ = get_our_mask_scores(data_bytes, version, ec_level)
    std_best, qr = get_std_best_mask(data_bytes, version, ec_level)
    
    print(f"  我们的评分: {our_scores}")
    print(f"  我们的最佳掩码: {our_best} (分数={our_scores[our_best]})")
    print(f"  标准库最佳掩码: {std_best}")
    
    if our_best == std_best:
        print(f"  最佳掩码一致 ✓")
        return True
    else:
        print(f"  最佳掩码不一致 ✗")
        # 看看标准库的掩码如果我们评分的话是多少
        print(f"  我们给标准最佳掩码的评分: {our_scores[std_best]} (排名: {sorted(our_scores).index(our_scores[std_best]) + 1}/8)")
        return False


def main():
    all_pass = True
    
    # 测试1：小数据
    data = b"Hello, World!"
    all_pass &= test_case("Hello World v1-L", data, 1, EC_LEVEL_L)
    
    # 测试2：中等数据
    data = b"Hello World! This is a test of QR code mask selection."
    all_pass &= test_case("中等数据 v2-M", data, 2, EC_LEVEL_M)
    
    # 测试3：版本7数据
    data = bytes(range(50))
    all_pass &= test_case("50字节 v7-M", data, 7, EC_LEVEL_M)
    
    # 测试4：各种数据
    test_datas = [
        (b"12345678", "数字 v1-L", 1, EC_LEVEL_L),
        (b"http://example.com", "网址 v1-M", 1, EC_LEVEL_M),
        (b"Test of N3 rule. Look for finder-like patterns.", "N3测试 v3-Q", 3, EC_LEVEL_Q),
    ]
    
    for data, name, ver, ecl in test_datas:
        all_pass &= test_case(name, data, ver, ecl)
    
    print(f"\n{'='*60}")
    if all_pass:
        print("全部测试通过！最佳掩码选择一致 ✓✓✓")
    else:
        print("存在测试失败！最佳掩码选择不一致 ✗")


if __name__ == '__main__':
    main()
