#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试RS纠错码前导零是否完整保留
"""

import qrcode
from qrcode_generator import (
    DataEncoder, ReedSolomon, QR_CAPACITY_TABLE,
    EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H,
)


def test_rs_leading_zero():
    """测试容易触发前导零的情况"""
    
    print("RS纠错码前导零测试")
    print("=" * 60)
    
    # 构造一些容易产生前导零EC码的测试数据
    # 全零数据容易产生全零EC码？不一定，让我们试试
    test_cases = []
    
    # 测试1: 全零数据
    test_cases.append(("全零数据 v1-L", bytes([0] * 10), 1, EC_LEVEL_L))
    
    # 测试2: 特定模式数据
    test_cases.append(("0x00-0x0F v1-M", bytes(range(16)), 1, EC_LEVEL_M))
    
    # 测试3: 版本7-M，更多块
    test_cases.append(("50字节 v7-M", b"\x00" * 50, 7, EC_LEVEL_M))
    
    # 测试4: 版本10-Q
    test_cases.append(("100字节 v10-Q", b"\x00" * 100, 10, EC_LEVEL_Q))
    
    # 测试5: 版本3-H 高纠错等级
    test_cases.append(("20字节 v3-H", b"\x00" * 20, 3, EC_LEVEL_H))
    
    all_pass = True
    
    for name, data, version, ec_level in test_cases:
        print(f"\n测试: {name}")
        
        # 我们的实现
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
        
        # 检查每个EC块的长度和前导零
        has_leading_zero = False
        for i, ec_block in enumerate(ec_blocks):
            if len(ec_block) != ec_per:
                print(f"  ✗ 块 {i} EC长度不对: 预期={len(ec_block)}, 应为 {ec_per}")
                all_pass = False
            if ec_block[0] == 0:
                has_leading_zero = True
                # 数一下有多少个前导零
                zero_count = 0
                for b in ec_block:
                    if b == 0:
                        zero_count += 1
                    else:
                        break
                print(f"  块 {i}: {zero_count}个前导零 (共{len(ec_block)}个EC码字)")
        
        if not has_leading_zero:
            print(f"  (没有前导零，不影响测试)")
        
        # 对比标准库
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
        qr.add_data(data, optimize=0)
        try:
            qr.make(fit=False)
        except Exception as e:
            print(f"  标准库报错: {e}")
            continue
        
        # 获取标准库的EC码
        # 从 data_cache 是数据+EC交织后的结果
        std_data = list(qr.data_cache)
        
        # 我们的交织结果
        interleaved_data = DataEncoder.interleave(blocks)
        interleaved_ec = DataEncoder.interleave(ec_blocks)
        our_data = interleaved_data + interleaved_ec
        
        # 对比
        if list(std_data) == our_data:
            print(f"  ✓ 数据+EC 与标准库完全一致")
        else:
            print(f"  ✗ 数据+EC 与标准库不一致")
            all_pass = False
            # 找第一个差异
            min_len = min(len(std_data), len(our_data))
            for i in range(min_len):
                if std_data[i] != our_data[i]:
                    print(f"    第一个差异位置 {i}: 标准={std_data[i]:02x}, 我们={our_data[i]:02x}")
                    break
            if len(std_data) != len(our_data):
                print(f"    长度不同: 标准={len(std_data)}, 我们={len(our_data)}")
    
    print("\n" + "=" * 60)
    if all_pass:
        print("全部通过！✓✓✓")
    else:
        print("存在问题！✗")
    
    return all_pass


if __name__ == '__main__':
    test_rs_leading_zero()
