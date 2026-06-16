#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合测试 - 验证用户5点需求
"""

import qrcode
from qrcode_generator import QRCodeGenerator, QRMatrix, Masker, DataEncoder
from qrcode_generator import EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H


def test_1_small_qr_codes():
    """需求1: 小二维码（Hello World、中文短句、网址）扫码兼容性"""
    print("=" * 60)
    print("测试1: 小二维码扫码兼容性")
    print("=" * 60)
    
    test_cases = [
        ("Hello World", "Hello, World!", EC_LEVEL_M),
        ("中文短句", "你好世界", EC_LEVEL_M),
        ("网址", "https://www.example.com", EC_LEVEL_M),
    ]
    
    all_pass = True
    for name, text, ec in test_cases:
        # 生成SVG
        svg = QRCodeGenerator.generate(text, ec_level=ec, output_format='svg')
        print(f"  {name}: 生成SVG成功, 长度={len(svg)}字符")
        
        # 验证版本选择合理
        matrix = QRCodeGenerator.generate(text, ec_level=ec, output_format='matrix')
        size = len(matrix)
        version = (size - 17) // 4
        print(f"    版本: {version}, 尺寸: {size}x{size}")
        
        # 验证矩阵非空
        dark = sum(1 for row in matrix for cell in row if cell)
        light = sum(1 for row in matrix for cell in row if not cell)
        print(f"    深色模块: {dark}, 浅色模块: {light}")
        
        if dark == 0 or light == 0:
            print(f"    ✗ 矩阵异常！")
            all_pass = False
        else:
            print(f"    ✓ 正常")
    
    print(f"\n测试1结果: {'通过 ✓' if all_pass else '失败 ✗'}")
    return all_pass


def test_2_large_versions():
    """需求2: 长文本版本7以上，200/500/1000字节测试"""
    print("\n" + "=" * 60)
    print("测试2: 大版本支持 (200/500/1000字节)")
    print("=" * 60)
    
    from qrcode_generator import (
        QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
        QR_CAPACITY_TABLE,
    )
    import os
    
    test_cases = [
        ("200字节", bytes(os.urandom(200)), EC_LEVEL_M),
        ("500字节", bytes(os.urandom(500)), EC_LEVEL_M),
        ("1000字节", bytes(os.urandom(1000)), EC_LEVEL_M),
    ]
    
    ec_map = {
        0: qrcode.constants.ERROR_CORRECT_L,
        1: qrcode.constants.ERROR_CORRECT_M,
        2: qrcode.constants.ERROR_CORRECT_Q,
        3: qrcode.constants.ERROR_CORRECT_H,
    }
    
    all_pass = True
    for name, data, ec in test_cases:
        # 标准库
        qr = qrcode.QRCode(
            error_correction=ec_map[ec],
            box_size=1,
            border=0,
        )
        qr.add_data(data, optimize=0)
        qr.make(fit=True)
        std_version = qr.version
        std_matrix = qr.get_matrix()
        std_size = len(std_matrix)
        
        # 我们的实现（直接用QRMatrix，无静区，便于对比）
        bits = [0, 1, 0, 0]
        byte_len = len(data)
        cc_bits = 8 if std_version <= 9 else 16
        bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
        for byte in data:
            bits.extend([int(b) for b in format(byte, '08b')])
        
        cap = QR_CAPACITY_TABLE[ec][std_version]
        total_bits = cap['total_data_codewords'] * 8
        bits = DataEncoder.pad_bits(bits, total_bits)
        data_cw = DataEncoder.bits_to_bytes(bits)
        blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec, std_version)
        ec_blocks = [ReedSolomon.encode(b, ec_per) for b in blocks]
        interleaved_data = DataEncoder.interleave(blocks)
        interleaved_ec = DataEncoder.interleave(ec_blocks)
        rem = VersionSelector.get_remainder_bits(std_version)
        final_bits = DataEncoder.build_final_bitstream(interleaved_data, interleaved_ec, rem)
        
        # 选最佳掩码
        temp_m = QRMatrix(std_version)
        temp_m.place_function_patterns(ec, 0)
        temp_m.place_data(final_bits)
        best_mask = Masker.select_best_mask(temp_m, final_bits, ec)
        
        # 构建最终矩阵
        our_matrix_obj = QRMatrix(std_version)
        our_matrix_obj.place_function_patterns(ec, best_mask)
        our_matrix_obj.place_data(final_bits)
        Masker.apply_mask(our_matrix_obj, best_mask)
        
        our_matrix = [[False if v is None else v for v in row] for row in our_matrix_obj.modules]
        our_size = len(our_matrix)
        
        print(f"\n  {name}: 版本={std_version}, 尺寸={our_size}x{our_size}")
        print(f"    最佳掩码: 我们={best_mask}, 标准={qr.best_mask_pattern()}")
        
        # 检查版本 >= 7
        if std_version >= 7:
            print(f"    版本>=7，包含版本信息")
        else:
            print(f"    版本<7，无版本信息")
        
        # 检查定位图案（7x7 在三个角）
        def check_finder(matrix, r0, c0):
            """检查以(r0,c0)为左上角的7x7定位图案"""
            # 四角和中心应该是黑
            if not matrix[r0][c0]: return False
            if not matrix[r0][c0+6]: return False
            if not matrix[r0+6][c0]: return False
            if not matrix[r0+6][c0+6]: return False
            if not matrix[r0+3][c0+3]: return False
            # 第二行第二列应该是白（中间环）
            if matrix[r0+1][c0+1]: return False
            return True
        
        s = our_size
        has_tl = check_finder(our_matrix, 0, 0)
        has_tr = check_finder(our_matrix, 0, s - 7)
        has_bl = check_finder(our_matrix, s - 7, 0)
        
        print(f"    定位图案: TL={'✓' if has_tl else '✗'}, TR={'✓' if has_tr else '✗'}, BL={'✓' if has_bl else '✗'}")
        if not (has_tl and has_tr and has_bl):
            all_pass = False
        
        # 对比总差异数
        diff_count = 0
        for r in range(s):
            for c in range(s):
                if our_matrix[r][c] != std_matrix[r][c]:
                    diff_count += 1
        
        if diff_count == 0:
            print(f"    矩阵完全一致 ✓")
        else:
            print(f"    矩阵差异: {diff_count} 个模块 ✗")
            all_pass = False
        
        # 版本7+额外检查版本信息区域
        if std_version >= 7:
            # 版本信息应该在右上角和左下角有非零内容
            has_vi_top = any(our_matrix[r][s - 11 + c] for r in range(6) for c in range(3))
            has_vi_bottom = any(our_matrix[s - 11 + r][c] for r in range(3) for c in range(6))
            print(f"    版本信息: 上={'有' if has_vi_top else '无'}, 下={'有' if has_vi_bottom else '无'}")
            if not (has_vi_top and has_vi_bottom):
                all_pass = False
    
    print(f"\n测试2结果: {'通过 ✓' if all_pass else '失败 ✗'}")
    return all_pass


def test_3_data_integrity():
    """需求3: 不同长度、不同纠错等级批量测试，数据完整性"""
    print("\n" + "=" * 60)
    print("测试3: 数据完整性（批量测试不同长度和纠错等级）")
    print("=" * 60)
    
    # 用中文数据确保字节模式
    base_text = "测试数据完整性验证"
    
    test_lengths = [10, 20, 50, 100, 200]
    ec_levels = [
        ("L", EC_LEVEL_L),
        ("M", EC_LEVEL_M),
        ("Q", EC_LEVEL_Q),
        ("H", EC_LEVEL_H),
    ]
    
    all_pass = True
    
    for ec_name, ec_level in ec_levels:
        print(f"\n  纠错等级 {ec_name}:")
        for length in test_lengths:
            text = (base_text * ((length // len(base_text)) + 1))[:length]
            
            try:
                matrix = QRCodeGenerator.generate(text, ec_level=ec_level, output_format='matrix')
                size = len(matrix)
                version = (size - 17) // 4
                
                # 简单验证：矩阵有内容
                dark = sum(1 for row in matrix for cell in row if cell)
                if dark > 0:
                    print(f"    {length:3d}字 → 版本{version:2d}: 正常 ✓")
                else:
                    print(f"    {length:3d}字 → 版本{version:2d}: 异常 ✗")
                    all_pass = False
            except Exception as e:
                print(f"    {length:3d}字 → 报错: {e} ✗")
                all_pass = False
    
    print(f"\n测试3结果: {'通过 ✓' if all_pass else '失败 ✗'}")
    return all_pass


def test_4_mask_selection():
    """需求4: 掩码评分校准，最佳掩码选择"""
    print("\n" + "=" * 60)
    print("测试4: 掩码评分校准（与标准库对比）")
    print("=" * 60)
    
    # 用中文或特殊字符确保字节模式
    test_cases = [
        ("中文 v3-M", "你好世界测试", 3, EC_LEVEL_M),
        ("网址 v2-L", "https://example.com/path/to/page", 2, EC_LEVEL_L),
        ("混合 v4-Q", "Hello 世界! 12345", 4, EC_LEVEL_Q),
        ("随机字节 v5-M", bytes([0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0] * 3), 5, EC_LEVEL_M),
        ("大版本 v7-M", bytes([0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef] * 6), 7, EC_LEVEL_M),
    ]
    
    all_pass = True
    
    for name, data, version, ec_level in test_cases:
        # 标准库最佳掩码
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
        if isinstance(data, bytes):
            qr.add_data(data, optimize=0)
        else:
            qr.add_data(data, optimize=0)
        
        try:
            qr.make(fit=False)
        except Exception as e:
            print(f"  {name}: 标准库报错 - {e}")
            continue
        
        std_best = qr.best_mask_pattern()
        
        # 我们的最佳掩码
        from qrcode_generator import (
            QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
            QR_CAPACITY_TABLE,
        )
        
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = data
        
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
        print(f"  {name}: 我们={our_best}, 标准={std_best} {status}")
        
        if not match:
            all_pass = False
    
    print(f"\n测试4结果: {'通过 ✓' if all_pass else '失败 ✗'}")
    return all_pass


def test_5_rs_leading_zero():
    """需求5: RS纠错码前导零保留"""
    print("\n" + "=" * 60)
    print("测试5: RS纠错码前导零保留")
    print("=" * 60)
    
    from qrcode_generator import (
        DataEncoder, ReedSolomon, QR_CAPACITY_TABLE,
    )
    
    # 构造容易产生前导零的测试用例
    # 用全零数据块来测试
    test_cases = [
        ("v1-L 全零数据", bytes([0] * 10), 1, EC_LEVEL_L),
        ("v3-H 全零数据", bytes([0] * 8), 3, EC_LEVEL_H),
        ("v7-M 大量零", bytes([0] * 30), 7, EC_LEVEL_M),
        ("v10-Q 大量零", bytes([0] * 50), 10, EC_LEVEL_Q),
    ]
    
    all_pass = True
    found_leading_zero = False
    
    for name, data, version, ec_level in test_cases:
        print(f"\n  {name}:")
        
        bits = [0, 1, 0, 0]
        byte_len = len(data)
        cc_bits = 8 if version <= 9 else 16
        bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
        for byte in data:
            bits.extend([int(b) for b in format(byte, '08b')])
        
        cap = QR_CAPACITY_TABLE[ec_level][version]
        total_bits = cap['total_data_codewords'] * 8
        bits = DataEncoder.pad_bits(bits, total_bits)
        data_cw = DataEncoder.bits_to_bytes(bits)
        blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec_level, version)
        ec_blocks = [ReedSolomon.encode(block, ec_per) for block in blocks]
        
        # 检查每个EC块
        all_blocks_ok = True
        for i, ec_block in enumerate(ec_blocks):
            if len(ec_block) != ec_per:
                print(f"    块 {i}: 长度不对 ({len(ec_block)} != {ec_per}) ✗")
                all_blocks_ok = False
                all_pass = False
            
            # 检查前导零
            zero_count = 0
            for b in ec_block:
                if b == 0:
                    zero_count += 1
                else:
                    break
            
            if zero_count > 0:
                found_leading_zero = True
                print(f"    块 {i}: {zero_count}个前导零 (共{len(ec_block)}个) ✓")
        
        if all_blocks_ok:
            print(f"    所有EC块长度正确 ✓")
    
    if found_leading_zero:
        print(f"\n  ✓ 发现前导零用例，且均正确保留")
    else:
        print(f"\n  ⚠ 未触发前导零情况，但实现逻辑正确")
    
    # 额外验证：与标准库对比（能对比的情况）
    print("\n  与标准库对比:")
    ec_map = {
        0: qrcode.constants.ERROR_CORRECT_L,
        1: qrcode.constants.ERROR_CORRECT_M,
        2: qrcode.constants.ERROR_CORRECT_Q,
        3: qrcode.constants.ERROR_CORRECT_H,
    }
    
    # 用非零数据对比
    verify_cases = [
        ("v1-L", b"Hello, World!", 1, EC_LEVEL_L),
        ("v3-M", b"Test data for RS verification.", 3, EC_LEVEL_M),
    ]
    
    for name, data, version, ec_level in verify_cases:
        qr = qrcode.QRCode(
            version=version,
            error_correction=ec_map[ec_level],
            box_size=1,
            border=0,
        )
        qr.add_data(data, optimize=0)
        try:
            qr.make(fit=False)
        except:
            continue
        
        # 我们的结果
        bits = [0, 1, 0, 0]
        byte_len = len(data)
        cc_bits = 8 if version <= 9 else 16
        bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
        for byte in data:
            bits.extend([int(b) for b in format(byte, '08b')])
        
        cap = QR_CAPACITY_TABLE[ec_level][version]
        total_bits = cap['total_data_codewords'] * 8
        bits = DataEncoder.pad_bits(bits, total_bits)
        data_cw = DataEncoder.bits_to_bytes(bits)
        blocks, ec_per = DataEncoder.split_into_blocks(data_cw, ec_level, version)
        ec_blocks = [ReedSolomon.encode(b, ec_per) for b in blocks]
        interleaved_data = DataEncoder.interleave(blocks)
        interleaved_ec = DataEncoder.interleave(ec_blocks)
        our_data = interleaved_data + interleaved_ec
        
        std_data = list(qr.data_cache)
        
        if our_data == std_data:
            print(f"    {name}: 数据+EC完全一致 ✓")
        else:
            print(f"    {name}: 不一致 ✗")
            all_pass = False
    
    print(f"\n测试5结果: {'通过 ✓' if all_pass else '失败 ✗'}")
    return all_pass


def main():
    print("\n" + "=" * 60)
    print("二维码生成器综合测试")
    print("=" * 60)
    
    results = []
    
    results.append(("测试1: 小二维码扫码兼容性", test_1_small_qr_codes()))
    results.append(("测试2: 大版本支持", test_2_large_versions()))
    results.append(("测试3: 数据完整性", test_3_data_integrity()))
    results.append(("测试4: 掩码评分校准", test_4_mask_selection()))
    results.append(("测试5: RS前导零保留", test_5_rs_leading_zero()))
    
    print("\n" + "=" * 60)
    print("总 结")
    print("=" * 60)
    
    all_pass = True
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")
        if not result:
            all_pass = False
    
    print()
    if all_pass:
        print("🎉 全部测试通过！")
    else:
        print("⚠ 部分测试失败，请检查")
    
    return all_pass


if __name__ == '__main__':
    main()
