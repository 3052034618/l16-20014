#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据放置顺序 - 从右下角开始逐位对比
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_NAMES, QR_CAPACITY_TABLE
)


def get_std_matrix(text, version, ec_level, mask_pattern=None, optimize=0):
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
    qr.add_data(text, optimize=optimize)
    qr.make(fit=True)
    return qr.get_matrix()


def get_our_matrix(text, version, ec_level, mask_num=0):
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
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, mask_num)
    m.place_data(final_bits)
    # 不应用掩码，直接看原始数据
    # Masker.apply_mask(m, mask_num)
    
    matrix = [[False if v is None else v for v in row] for row in m.modules]
    return matrix, final_bits, m.is_function


def list_data_modules_in_order(is_func, size):
    """按蛇形顺序列出所有数据模块的坐标"""
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
    # 用版本1-L，数据量小，容易对比
    text = "A"
    version = 1
    ec_level = EC_LEVEL_L
    mask_num = 0  # 用掩码0，数据不变
    
    print("=" * 70)
    print(f"对比测试：文本='{text}', 版本{version}-{EC_LEVEL_NAMES[ec_level]}, 掩码{mask_num}")
    print("=" * 70)
    
    # 我们的实现（不应用掩码）
    our_matrix, our_bits, is_func = get_our_matrix(text, version, ec_level, mask_num)
    s = len(our_matrix)
    print(f"矩阵大小: {s}x{s}")
    
    # 按顺序列出数据模块
    data_coords = list_data_modules_in_order(is_func, s)
    print(f"数据模块总数: {len(data_coords)}")
    
    # 我们的前20位数据
    print(f"\n我们的前20位数据（按放置顺序）：")
    our_data_bits = []
    for r, c in data_coords[:20]:
        our_data_bits.append(1 if our_matrix[r][c] else 0)
    print(f"  {''.join(str(b) for b in our_data_bits)}")
    
    # 我们的比特流前20位
    print(f"我们的比特流前20位：")
    print(f"  {''.join(str(b) for b in our_bits[:20])}")
    
    # 期望的字节模式
    text_bytes = text.encode('utf-8')
    expected = [0, 1, 0, 0]  # 字节模式
    byte_len = len(text_bytes)
    cc_bits = 8 if version <= 9 else 16
    expected.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
    for byte in text_bytes:
        expected.extend([int(b) for b in format(byte, '08b')])
    print(f"\n期望的前20位：")
    print(f"  {''.join(str(b) for b in expected[:20])}")
    
    # 标准库的
    print(f"\n--- 标准库 ---")
    std_matrix = get_std_matrix(text, version, ec_level, mask_pattern=mask_num, optimize=0)
    
    # 标准库前20位数据（按我们的顺序）
    print(f"标准库前20位数据（按我们的顺序）：")
    std_data_bits = []
    for r, c in data_coords[:20]:
        std_data_bits.append(1 if std_matrix[r][c] else 0)
    print(f"  {''.join(str(b) for b in std_data_bits)}")
    
    # 找第一个数据位的位置
    # 我们手动找一下标准库中第一个数据模块
    # 先打印右下角区域
    print(f"\n右下角区域 (行{s-5}到{s-1}, 列{s-5}到{s-1})：")
    print("      ", end="")
    for c in range(s-5, s):
        print(f"{c:3d}", end="")
    print()
    for r in range(s-5, s):
        print(f"行{r:2d}: ", end="")
        for c in range(s-5, s):
            val = '█' if std_matrix[r][c] else '·'
            is_f = is_func[r][c]
            if is_f:
                val = val + 'f'
            else:
                val = val + ' '
            print(f" {val}", end="")
        print()
    
    # 检查我们的右下角
    print(f"\n我们的右下角 (行{s-5}到{s-1}, 列{s-5}到{s-1})：")
    print("      ", end="")
    for c in range(s-5, s):
        print(f"{c:3d}", end="")
    print()
    for r in range(s-5, s):
        print(f"行{r:2d}: ", end="")
        for c in range(s-5, s):
            val = '█' if our_matrix[r][c] else '·'
            is_f = is_func[r][c]
            if is_f:
                val = val + 'f'
            else:
                val = val + ' '
            print(f" {val}", end="")
        print()
    
    # 数据坐标前10个
    print(f"\n前10个数据坐标（按我们的顺序）：")
    for i, (r, c) in enumerate(data_coords[:10]):
        print(f"  第{i}位: ({r}, {c})  我们:{1 if our_matrix[r][c] else 0}  标准:{1 if std_matrix[r][c] else 0}")


if __name__ == '__main__':
    main()
