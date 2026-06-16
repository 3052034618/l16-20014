#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比最佳掩码选择
"""

import qrcode
from qrcode_generator import QRCodeGenerator, EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H


def test_case(name, data_bytes, version, ec_level):
    """测试一个用例（使用原始字节，确保两边都是字节模式）"""
    # 标准库
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
    qr.add_data(data_bytes, optimize=0)
    qr.make(fit=False)
    std_best = qr.best_mask_pattern()
    
    # 我们的 - 直接生成
    from qrcode_generator import (
        QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
        QR_CAPACITY_TABLE,
    )
    
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
    
    temp_matrix = QRMatrix(version)
    temp_matrix.place_function_patterns(ec_level, 0)
    temp_matrix.place_data(final_bits)
    our_best = Masker.select_best_mask(temp_matrix, final_bits, ec_level)
    
    match = our_best == std_best
    status = "✓" if match else "✗"
    
    print(f"  {name}: 我们的最佳掩码={our_best}, 标准最佳掩码={std_best} {status}")
    
    return match


def main():
    print("最佳掩码选择对比测试")
    print()
    
    all_pass = True
    
    test_cases = [
        ("中文 v3-M", "你好世界".encode('utf-8'), 3, EC_LEVEL_M),
        ("中文 v4-Q", "测试中文编码测试".encode('utf-8'), 4, EC_LEVEL_Q),
        ("特殊字符 v2-M", "Hello, 世界! 123".encode('utf-8'), 2, EC_LEVEL_M),
        ("网址 v2-M", "https://example.com/test".encode('utf-8'), 2, EC_LEVEL_M),
        ("50字节 v5-M", b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09" * 5, 5, EC_LEVEL_M),
        ("100字节 v7-M", b"\x12\x34\x56\x78" * 25, 7, EC_LEVEL_M),
    ]
    
    for name, data, ver, ecl in test_cases:
        all_pass &= test_case(name, data, ver, ecl)
    
    print()
    if all_pass:
        print("全部通过！✓✓✓")
    else:
        print("存在不一致！✗")


if __name__ == '__main__':
    main()
