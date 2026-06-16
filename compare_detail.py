#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细对比差异位置
"""

import qrcode
from qrcode_generator import (
    QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_NAMES, QR_CAPACITY_TABLE
)


def get_std_matrix(data_bytes, version, ec_level, mask_pattern=0):
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
    qr.add_data(data_bytes)
    qr.make(fit=True)
    return qr.get_matrix()


def get_our_matrix(data_bytes, version, ec_level, mask_num=0):
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
    return matrix, final_bits, m.is_function, data_cw, ec_blocks[0]


def list_data_modules_in_order(is_func, size):
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
    data = bytes([0x12, 0x34, 0x56, 0x78])
    version = 1
    ec_level = EC_LEVEL_L
    mask_num = 0
    
    std_matrix = get_std_matrix(data, version, ec_level, mask_pattern=mask_num)
    our_matrix, our_bits, is_func, data_cw, ec_cw = get_our_matrix(data, version, ec_level, mask_num)
    s = len(std_matrix)
    
    data_coords = list_data_modules_in_order(is_func, s)
    print(f"数据模块数（我们的统计）: {len(data_coords)}")
    
    # 计算标准的总数据位
    cap = QR_CAPACITY_TABLE[ec_level][version]
    num_blocks = cap['num_blocks_g1'] + cap['num_blocks_g2']
    total_cw = cap['total_data_codewords'] + cap['ec_per_block'] * num_blocks
    total_bits_std = total_cw * 8 + VersionSelector.get_remainder_bits(version)
    print(f"标准总数据位: {total_bits_std}")
    print(f"  总数据码字: {cap['total_data_codewords']}")
    print(f"  EC码字: {cap['ec_per_block']} x {num_blocks} = {cap['ec_per_block'] * num_blocks}")
    print(f"  余位: {VersionSelector.get_remainder_bits(version)}")
    
    # 列出所有差异
    print(f"\n所有差异（共7个）：")
    diffs = []
    for i, (r, c) in enumerate(data_coords):
        sv = std_matrix[r][c]
        ov = our_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            sv_data = not sv
            ov_data = not ov
        else:
            sv_data = sv
            ov_data = ov
        if sv != ov:
            diffs.append((i, r, c, 1 if sv_data else 0, 1 if ov_data else 0))
    
    for i, r, c, sv, ov in diffs:
        print(f"  第{i}位 ({r},{c}): 标准={sv} 我们={ov}")
    
    # 检查第152位之后（纠错码区域开始）
    print(f"\n数据码字结束位置: {cap['total_data_codewords'] * 8} 位")
    print(f"第152位附近：")
    for i in range(148, 160):
        if i < len(data_coords):
            r, c = data_coords[i]
            sv = std_matrix[r][c]
            ov = our_matrix[r][c]
            if Masker.mask_function(mask_num, r, c):
                sv_data = not sv
                ov_data = not ov
            else:
                sv_data = sv
                ov_data = ov
            mark = " ◄" if sv != ov else ""
            print(f"  第{i}位 ({r},{c}): 标准={1 if sv_data else 0} 我们={1 if ov_data else 0}{mark}")
    
    # 我们的纠错码
    print(f"\n我们的数据码字: {[hex(b) for b in data_cw]}")
    print(f"我们的EC码字: {[hex(b) for b in ec_cw]}")
    
    # 从标准库提取纠错码
    # 先提取所有数据位（去掩码后）
    std_all_bits = []
    for r, c in data_coords:
        sv = std_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            sv = not sv
        std_all_bits.append(1 if sv else 0)
    
    # 转换为字节
    std_bytes = []
    for i in range(0, len(std_all_bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | std_all_bits[i + j]
        std_bytes.append(byte)
    
    print(f"\n从标准库提取的前26字节：")
    print(f"  {[hex(b) for b in std_bytes[:26]]}")
    
    # 我们的完整字节流
    our_all_bits = []
    for r, c in data_coords:
        ov = our_matrix[r][c]
        if Masker.mask_function(mask_num, r, c):
            ov = not ov
        our_all_bits.append(1 if ov else 0)
    
    our_bytes = []
    for i in range(0, len(our_all_bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | our_all_bits[i + j]
        our_bytes.append(byte)
    
    print(f"我们的前26字节：")
    print(f"  {[hex(b) for b in our_bytes[:26]]}")


if __name__ == '__main__':
    main()
