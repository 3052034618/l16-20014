#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细诊断：对比标准库和我们的实现，找出具体差异原因
"""

import qrcode
import sys
sys.path.insert(0, '.')
from qrcode_generator import (
    QRCodeGenerator, QRMatrix, DataEncoder, ReedSolomon, Masker,
    VersionSelector, EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H,
    EC_LEVEL_NAMES, QR_CAPACITY_TABLE,
)


def test_format_info():
    """测试格式信息编码"""
    print("=" * 70)
    print("测试1：格式信息编码")
    print("=" * 70)
    
    # 用标准库生成一个，提取格式信息
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=1, border=0)
    qr.add_data("A")
    qr.make(fit=False)
    std = qr.get_matrix()
    
    s = len(std)
    print(f"标准库版本1-M，大小{s}x{s}")
    
    # 提取格式信息（位置1：行8和列8）
    fmt1 = []
    # 行8，列0-8（跳过列6）
    for c in [0, 1, 2, 3, 4, 5, 7, 8]:
        fmt1.append(1 if std[8][c] else 0)
    # 列8，行7-0（跳过行6）
    for r in [7, 5, 4, 3, 2, 1, 0]:
        fmt1.append(1 if std[r][8] else 0)
    
    print(f"\n标准库 格式信息（位置1，共{len(fmt1)}位）:")
    print(f"  {''.join(str(b) for b in fmt1)}")
    
    # 位置2
    fmt2 = []
    # 列8，行s-7到s-1
    for r in range(s-7, s):
        fmt2.append(1 if std[r][8] else 0)
    # 行8，列s-8到s-1
    for c in range(s-8, s):
        fmt2.append(1 if std[8][c] else 0)
    
    print(f"标准库 格式信息（位置2，共{len(fmt2)}位）:")
    print(f"  {''.join(str(b) for b in fmt2)}")
    
    # 我们的格式信息
    print(f"\n我们的实现 - 格式信息测试:")
    for mask in range(8):
        m = QRMatrix(1)
        m.place_function_patterns(EC_LEVEL_M, mask)
        
        our_fmt = []
        for c in [0, 1, 2, 3, 4, 5, 7, 8]:
            our_fmt.append(1 if m.modules[8][c] else 0)
        for r in [7, 5, 4, 3, 2, 1, 0]:
            our_fmt.append(1 if m.modules[r][8] else 0)
        
        match = "✓" if our_fmt == fmt1 else "✗"
        print(f"  掩码{mask}: {''.join(str(b) for b in our_fmt)} {match}")


def test_data_encoding():
    """测试数据编码"""
    print("\n" + "=" * 70)
    print("测试2：数据编码（字节模式）")
    print("=" * 70)
    
    text = "Hello"
    version = 2
    ec_level = EC_LEVEL_M
    
    # 我们的编码
    bits, cc = DataEncoder.encode_byte_mode(text)
    bits = DataEncoder.adjust_char_count_indicator(bits, cc, version)
    cap = QR_CAPACITY_TABLE[ec_level][version]
    total_bits = cap['total_data_codewords'] * 8
    bits = DataEncoder.pad_bits(bits, total_bits)
    data_cw = DataEncoder.bits_to_bytes(bits)
    
    print(f"文本: '{text}', 版本: {version}, 纠错: {EC_LEVEL_NAMES[ec_level]}")
    print(f"总数据码字数: {cap['total_data_codewords']}")
    print(f"我们的数据码字 ({len(data_cw)}):")
    print(f"  {[hex(x) for x in data_cw]}")
    
    # 用标准库反推数据码字
    qr = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=1, border=0)
    qr.add_data(text)
    qr.make(fit=False)
    
    # 从标准库的QR对象中直接获取数据
    print(f"\n标准库内部数据:")
    print(f"  data_list: {qr.data_list}")
    print(f"  data_cache: {qr.data_cache is not None}")
    
    # 查看标准库源码中的数据生成
    # 直接访问内部属性
    if hasattr(qr, 'data_cache') and qr.data_cache:
        print(f"  data_cache 长度: {len(qr.data_cache)}")
    
    # 对比数据分块
    blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec_level, version)
    print(f"\n我们的分块:")
    print(f"  块数: {len(blocks)}, 每块纠错码: {ec_per}")
    for i, b in enumerate(blocks):
        print(f"  块{i}: {[hex(x) for x in b]}")


def test_rs_encoding():
    """测试RS编码"""
    print("\n" + "=" * 70)
    print("测试3：RS纠错编码")
    print("=" * 70)
    
    # 测试已知数据
    test_data = [0x10, 0x20, 0x0C, 0x56, 0x61, 0x80, 0xEC, 0x11]
    nsym = 10
    
    ec = ReedSolomon.encode(test_data, nsym)
    print(f"测试数据: {[hex(x) for x in test_data]}")
    print(f"纠错码字数: {nsym}")
    print(f"我们的RS结果: {[hex(x) for x in ec]}")
    print(f"结果长度: {len(ec)}")
    
    # 用标准库验证
    print(f"\n标准库验证（间接）:")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=1, border=0)
    qr.add_data("A")
    qr.make(fit=False)
    print(f"版本1-H 总模块数: {len(qr.get_matrix())}x{len(qr.get_matrix())}")


def test_data_placement():
    """测试数据放置顺序"""
    print("\n" + "=" * 70)
    print("测试4：数据放置顺序对比")
    print("=" * 70)
    
    text = "Hello"
    version = 2
    ec_level = EC_LEVEL_M
    
    # 标准库
    qr = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=1, border=0, mask_pattern=4)
    qr.add_data(text)
    qr.make(fit=False)
    std = qr.get_matrix()
    s = len(std)
    
    # 我们的 - 用掩码4
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
    m.place_function_patterns(ec_level, 4)
    m.place_data(final_bits)
    Masker.apply_mask(m, 4)
    
    our = [[False if v is None else v for v in row] for row in m.modules]
    
    # 统计数据区域的差异（排除功能区域）
    print(f"版本{version}-M-掩码4, 数据总位数: {len(final_bits)}")
    
    # 找数据区域的差异（只看非功能模块）
    # 先确定功能模块位置
    is_func = m.is_function
    
    data_diff_count = 0
    data_diffs = []
    
    for r in range(s):
        for c in range(s):
            if not is_func[r][c]:
                if std[r][c] != our[r][c]:
                    data_diff_count += 1
                    if len(data_diffs) < 15:
                        # 反推这是第几个数据位
                        data_diffs.append((r, c, std[r][c], our[r][c]))
    
    print(f"数据区域差异数: {data_diff_count}")
    if data_diffs:
        print("  前几个数据差异 (行,列, 标准, 我们):")
        for r, c, sv, ov in data_diffs:
            print(f"    ({r},{c}): {'1' if sv else '0'} vs {'1' if ov else '0'}")
    
    # 检查：是不是前N位数据对不上？
    # 从右下角开始，提取我们放置的前几位数据
    print(f"\n从右下角开始，提取前16位数据（去除掩码后）:")
    
    # 先取消掩码
    unmasked_std = []
    unmasked_our = []
    
    # 模拟数据放置顺序，提取位
    bit_count = 0
    col_pair = 0
    while bit_count < 16:
        right_col = s - 1 - col_pair * 2
        left_col = right_col - 1
        if left_col == 6:
            left_col = 5
        upward = (col_pair % 2 == 0)
        
        rows = range(s - 1, -1, -1) if upward else range(s)
        
        for row in rows:
            for c in [right_col, left_col]:
                if bit_count >= 16:
                    break
                if not is_func[row][c]:
                    # 标准库：去掩码
                    sv = std[row][c]
                    if Masker.mask_function(4, row, c):
                        sv = not sv
                    unmasked_std.append(1 if sv else 0)
                    
                    # 我们的：去掩码
                    ov = our[row][c]
                    if Masker.mask_function(4, row, c):
                        ov = not ov
                    unmasked_our.append(1 if ov else 0)
                    
                    bit_count += 1
        col_pair += 1
    
    print(f"  标准库(去掩码): {''.join(str(b) for b in unmasked_std)}")
    print(f"  我们的(去掩码): {''.join(str(b) for b in unmasked_our)}")
    
    # 期望的前16位：0100 + 字符数(8位) + 第一个字节的高4位
    expected = [0, 1, 0, 0]  # 模式
    # 字符数=5, 8位: 00000101
    char_count = 5
    expected.extend([int(b) for b in format(char_count, '08b')])
    # 'H' = 0x48 = 01001000
    expected.extend([0, 1, 0, 0])
    
    print(f"  期望值(前16位): {''.join(str(b) for b in expected)}")


def main():
    test_format_info()
    test_data_encoding()
    test_rs_encoding()
    test_data_placement()


if __name__ == '__main__':
    main()
