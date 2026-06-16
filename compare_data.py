#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细对比数据区域，找出差异原因
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_M, EC_LEVEL_NAMES, QR_CAPACITY_TABLE
)


def get_std_matrix(text, version, ec_level, mask_pattern=None):
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
    qr.add_data(text)
    qr.make(fit=True)
    return qr.get_matrix()


def get_our_matrix(text, version, ec_level, mask_num=None):
    bits, cc = DataEncoder.encode_byte_mode(text)
    bits = DataEncoder.adjust_char_count_indicator(bits, cc, version)
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
    
    if mask_num is None:
        temp = QRMatrix(version)
        temp.place_function_patterns(ec_level, 0)
        temp.place_data(final_bits)
        mask_num = Masker.select_best_mask(temp, final_bits, ec_level)
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, mask_num)
    m.place_data(final_bits)
    Masker.apply_mask(m, mask_num)
    
    matrix = [[False if v is None else v for v in row] for row in m.modules]
    return matrix, mask_num, final_bits, m.is_function


def extract_data_bits(matrix, is_func, size):
    """按标准放置顺序提取数据位（去掩码后）"""
    bits = []
    col_pair = 0
    while len(bits) < 100:  # 提取前100位
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
                    bits.append(1 if matrix[row][c] else 0)
                    if len(bits) >= 100:
                        return bits
        col_pair += 1
    return bits


def main():
    text = "Hello"
    version = 2
    ec_level = EC_LEVEL_M
    
    print("=" * 70)
    print(f"对比测试：文本='{text}', 版本{version}-{EC_LEVEL_NAMES[ec_level]}")
    print("=" * 70)
    
    # 先找出标准库用的掩码
    print("\n找出标准库使用的掩码：")
    std_matrix = get_std_matrix(text, version, ec_level)
    s = len(std_matrix)
    print(f"标准库矩阵大小: {s}x{s}")
    
    # 从格式信息反推掩码
    # 位置1提取格式信息
    fmt1 = []
    for c in [0, 1, 2, 3, 4, 5, 7, 8]:
        fmt1.append(1 if std_matrix[8][c] else 0)
    for r in [7, 5, 4, 3, 2, 1, 0]:
        fmt1.append(1 if std_matrix[r][8] else 0)
    
    fmt_value = 0
    for b in fmt1:
        fmt_value = (fmt_value << 1) | b
    # 异或掩码
    fmt_value ^= 0b101010000010010
    # 提取掩码（低3位）
    std_mask = fmt_value & 0b111
    print(f"从格式信息反推标准库掩码: {std_mask}")
    print(f"格式信息(去掩码后): {bin(fmt_value)[2:].zfill(15)}")
    
    # 用相同掩码生成我们的
    our_matrix, our_mask, our_bits, is_func = get_our_matrix(text, version, ec_level, std_mask)
    print(f"我们的掩码: {our_mask}")
    
    # 统计总差异
    diff_count = 0
    diffs = []
    for r in range(s):
        for c in range(s):
            if std_matrix[r][c] != our_matrix[r][c]:
                diff_count += 1
                if len(diffs) < 10:
                    diffs.append((r, c, std_matrix[r][c], our_matrix[r][c]))
    
    print(f"\n总差异数: {diff_count}")
    if diffs:
        print("前10个差异 (行,列, 标准, 我们):")
        for r, c, sv, ov in diffs:
            print(f"  ({r},{c}): {1 if sv else 0} vs {1 if ov else 0}")
    
    # 数据区域差异
    data_diff = 0
    for r in range(s):
        for c in range(s):
            if not is_func[r][c]:
                if std_matrix[r][c] != our_matrix[r][c]:
                    data_diff += 1
    print(f"数据区域差异: {data_diff}")
    
    # 提取数据位对比
    print(f"\n前50位数据对比（去掩码前）：")
    std_bits_raw = []
    our_bits_raw = []
    col_pair = 0
    count = 0
    while count < 50:
        right_col = s - 1 - col_pair * 2
        left_col = right_col - 1
        if left_col == 6:
            left_col = 5
        if right_col <= 0:
            break
        
        upward = (col_pair % 2 == 0)
        rows = range(s - 1, -1, -1) if upward else range(size) if False else range(s)
        
        for row in rows:
            for c in [right_col, left_col]:
                if not is_func[row][c]:
                    std_bits_raw.append(1 if std_matrix[row][c] else 0)
                    our_bits_raw.append(1 if our_matrix[row][c] else 0)
                    count += 1
                    if count >= 50:
                        break
            if count >= 50:
                break
        col_pair += 1
    
    print(f"  标准库: {''.join(str(b) for b in std_bits_raw)}")
    print(f"  我们的: {''.join(str(b) for b in our_bits_raw)}")
    
    # 去掩码后
    print(f"\n前50位数据对比（去掩码后）：")
    std_bits_unmasked = []
    our_bits_unmasked = []
    col_pair = 0
    count = 0
    while count < 50:
        right_col = s - 1 - col_pair * 2
        left_col = right_col - 1
        if left_col == 6:
            left_col = 5
        if right_col <= 0:
            break
        
        upward = (col_pair % 2 == 0)
        rows = range(s - 1, -1, -1) if upward else range(s)
        
        for row in rows:
            for c in [right_col, left_col]:
                if not is_func[row][c]:
                    sv = std_matrix[row][c]
                    ov = our_matrix[row][c]
                    if Masker.mask_function(std_mask, row, c):
                        sv = not sv
                        ov = not ov
                    std_bits_unmasked.append(1 if sv else 0)
                    our_bits_unmasked.append(1 if ov else 0)
                    count += 1
                    if count >= 50:
                        break
            if count >= 50:
                break
        col_pair += 1
    
    print(f"  标准库: {''.join(str(b) for b in std_bits_unmasked)}")
    print(f"  我们的: {''.join(str(b) for b in our_bits_unmasked)}")
    
    # 期望的前几位
    expected = [0, 1, 0, 0]  # 模式 0100
    char_count = len(text.encode('utf-8'))
    cc_bits = [int(b) for b in format(char_count, '08b')]
    expected.extend(cc_bits)
    for byte in text.encode('utf-8'):
        expected.extend([int(b) for b in format(byte, '08b')])
    print(f"  期望值: {''.join(str(b) for b in expected[:50])}")
    
    # 检查第一个差异位置
    first_diff = -1
    for i in range(min(len(std_bits_unmasked), len(our_bits_unmasked))):
        if std_bits_unmasked[i] != our_bits_unmasked[i]:
            first_diff = i
            break
    if first_diff >= 0:
        print(f"\n第一个差异在第 {first_diff} 位")
    else:
        print(f"\n前50位完全一致！")


if __name__ == '__main__':
    main()
