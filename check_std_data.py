#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查标准库的数据编码
"""

import qrcode

# 测试数据
data = b"A" * 10
version = 1

qr = qrcode.QRCode(
    version=version,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=1,
    border=0,
)
qr.add_data(data)
qr.make(fit=False)

# 查看 data_cache
print("data_cache 长度:", len(qr.data_cache))
print("data_cache 类型:", type(qr.data_cache[0]) if qr.data_cache else "empty")
print("前20个十六进制:", ' '.join(f'{x:02x}' for x in qr.data_cache[:20]))

# 查看 data_list
print("\ndata_list:")
for item in qr.data_list:
    print(f"  mode={item.mode}, data={item.data}, len={len(item.data) if hasattr(item.data, '__len__') else '?'}")

# 我们的数据
from qrcode_generator import (
    DataEncoder, ReedSolomon, VersionSelector,
    QR_CAPACITY_TABLE, EC_LEVEL_M,
)

bits = [0, 1, 0, 0]
byte_len = len(data)
cc_bits = 8 if version <= 9 else 16
bits.extend([int(b) for b in format(byte_len, f'0{cc_bits}b')])
for byte in data:
    bits.extend([int(b) for b in format(byte, '08b')])

cap = QR_CAPACITY_TABLE[EC_LEVEL_M][version]
total_bits = cap['total_data_codewords'] * 8
bits = DataEncoder.pad_bits(bits, total_bits)
data_cw = DataEncoder.bits_to_bytes(bits)

print(f"\n我们的数据码字: {len(data_cw)} 个")
print("前20个十六进制:", ' '.join(f'{x:02x}' for x in data_cw[:20]))

# 也看看总数据容量
print(f"\n版本{version}-M总数据码字: {cap['total_data_codewords']}")
print(f"版本{version}-M纠错码字每块: {cap['ec_codewords_per_block']}")
print(f"版本{version}-M块数 g1: {cap['num_blocks_g1']}, g2: {cap['num_blocks_g2']}")

# 标准库的 ec_codewords 和 blocks
print(f"\n标准库 error_correction: {qr.error_correction}")
print(f"标准库 total_logical_modules: {qr.modules_count}")
