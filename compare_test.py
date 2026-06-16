#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比测试：将我们的实现与标准 qrcode 库逐模块对比
"""

import qrcode
import sys
sys.path.insert(0, '.')
from qrcode_generator import (
    QRCodeGenerator, QRMatrix, DataEncoder, ReedSolomon, Masker,
    VersionSelector, EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H,
    EC_LEVEL_NAMES, FORMAT_INFO_MASK, FORMAT_INFO_GEN_POLY
)


def get_std_matrix(text, version, ec_level):
    """获取标准库生成的矩阵（无安静区）"""
    ec_map = {
        EC_LEVEL_L: qrcode.constants.ERROR_CORRECT_L,
        EC_LEVEL_M: qrcode.constants.ERROR_CORRECT_M,
        EC_LEVEL_Q: qrcode.constants.ERROR_CORRECT_Q,
        EC_LEVEL_H: qrcode.constants.ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(
        version=version,
        error_correction=ec_map[ec_level],
        box_size=1,
        border=0,
    )
    qr.add_data(text)
    qr.make(fit=False)
    matrix = qr.get_matrix()
    # 转换为 bool 矩阵
    return [[bool(x) for x in row] for row in matrix]


def get_our_matrix(text, version, ec_level, mask_num=None):
    """获取我们实现的矩阵（无安静区）"""
    # 手动构建以控制掩码
    bits, cc = DataEncoder.encode_byte_mode(text)
    bits = DataEncoder.adjust_char_count_indicator(bits, cc, version)
    cap = QR_CAPACITY_TABLE_OLD[ec_level][version]
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
        # 自动选最佳
        temp = QRMatrix(version)
        temp.place_function_patterns(ec_level, 0)
        temp.place_data(final_bits)
        mask_num = Masker.select_best_mask(temp, final_bits, ec_level)
    
    matrix = QRMatrix(version)
    matrix.place_function_patterns(ec_level, mask_num)
    matrix.place_data(final_bits)
    Masker.apply_mask(matrix, mask_num)
    
    return [[False if v is None else v for v in row] for row in matrix.modules], mask_num


def compare_matrices(std, our, label=""):
    """对比两个矩阵，返回差异统计"""
    size = len(std)
    diff_count = 0
    diffs = []
    for r in range(size):
        for c in range(size):
            if std[r][c] != our[r][c]:
                diff_count += 1
                if len(diffs) < 20:
                    diffs.append((r, c, std[r][c], our[r][c]))
    return diff_count, diffs


def print_matrix_region(matrix, r0, r1, c0, c1, title=""):
    """打印矩阵的一个区域"""
    print(f"\n=== {title} ===")
    for r in range(r0, r1+1):
        row = ""
        for c in range(c0, c1+1):
            if 0 <= r < len(matrix) and 0 <= c < len(matrix[r]):
                row += "█" if matrix[r][c] else "·"
            else:
                row += " "
        print(row)


# 临时导入旧容量表
from qrcode_generator import QR_CAPACITY_TABLE as QR_CAPACITY_TABLE_OLD


def main():
    print("=" * 70)
    print("二维码实现对比测试")
    print("=" * 70)
    
    test_cases = [
        ("Hello", 2, EC_LEVEL_M, "短文本-版本2-M"),
        ("Hello, World!", 3, EC_LEVEL_L, "短文本-版本3-L"),
        ("https://example.com/test/123", 5, EC_LEVEL_H, "URL-版本5-H"),
    ]
    
    for text, version, ec_level, desc in test_cases:
        print(f"\n{'=' * 70}")
        print(f"测试: {desc}")
        print(f"文本: '{text}', 版本: {version}, 纠错: {EC_LEVEL_NAMES[ec_level]}")
        print("-" * 70)
        
        # 标准库
        std_matrix = get_std_matrix(text, version, ec_level)
        std_size = len(std_matrix)
        print(f"标准库矩阵大小: {std_size}x{std_size}")
        
        # 我们的实现 - 先试试能不能找到匹配的掩码
        best_match_mask = -1
        min_diff = float('inf')
        
        for mask in range(8):
            our_matrix, _ = get_our_matrix(text, version, ec_level, mask)
            diff_count, diffs = compare_matrices(std_matrix, our_matrix)
            if diff_count < min_diff:
                min_diff = diff_count
                best_match_mask = mask
        
        print(f"最接近标准的掩码: {best_match_mask}, 差异数: {min_diff}")
        
        # 用最佳掩码再生成一次详细对比
        our_matrix, _ = get_our_matrix(text, version, ec_level, best_match_mask)
        diff_count, diffs = compare_matrices(std_matrix, our_matrix)
        
        if diff_count == 0:
            print("✓ 完全一致！")
        else:
            print(f"✗ 有 {diff_count} 个模块不同")
            print("  前几个差异点 (行, 列, 标准值, 我们的值):")
            for r, c, sv, ov in diffs[:10]:
                print(f"    ({r}, {c}): {'█' if sv else '·'} vs {'█' if ov else '·'}")
            
            # 打印左上角区域
            print_matrix_region(std_matrix, 0, 10, 0, 10, "标准库 - 左上角11x11")
            print_matrix_region(our_matrix, 0, 10, 0, 10, "我们的 - 左上角11x11")
            
            # 打印差异矩阵
            print_matrix_region(
                [[std_matrix[r][c] != our_matrix[r][c] for c in range(std_size)] for r in range(std_size)],
                0, std_size-1, 0, std_size-1, "差异图 (█=不同)"
            )
    
    # 测试版本7+的版本信息
    print(f"\n{'=' * 70}")
    print("测试版本7+版本信息")
    print("=" * 70)
    
    long_text = "A" * 150
    for version in [7, 8, 10]:
        print(f"\n版本 {version}:")
        try:
            std_matrix = get_std_matrix(long_text, version, EC_LEVEL_M)
            our_matrix, mask = get_our_matrix(long_text, version, EC_LEVEL_M)
            diff_count, diffs = compare_matrices(std_matrix, our_matrix)
            print(f"  标准掩码？我们的掩码: {mask}")
            print(f"  差异数: {diff_count}")
            if diff_count < 50:
                for r, c, sv, ov in diffs[:15]:
                    print(f"    ({r},{c}): {'█' if sv else '·'} vs {'█' if ov else '·'}")
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
    
    # 测试RS编码前导零
    print(f"\n{'=' * 70}")
    print("测试RS编码前导零问题")
    print("=" * 70)
    
    # 找一个会产生前导零的例子
    test_data = [0] * 10  # 全零数据
    nsym = 10
    ec = ReedSolomon.encode(test_data, nsym)
    print(f"全零数据(10字节), 纠错码字数={nsym}")
    print(f"  纠错码字: {ec}")
    print(f"  长度: {len(ec)} (期望: {nsym})")
    
    test_data2 = [1] * 5
    nsym2 = 8
    ec2 = ReedSolomon.encode(test_data2, nsym2)
    print(f"\n数据={test_data2}, 纠错码字数={nsym2}")
    print(f"  纠错码字: {ec2}")
    print(f"  长度: {len(ec2)} (期望: {nsym2})")


if __name__ == '__main__':
    main()
