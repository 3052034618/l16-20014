#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试RS编码 - 对比不同生成多项式的结果
"""

import qrcode
from qrcode_generator import GaloisField


def multiply_polys(a, b):
    result = [0] * (len(a) + len(b) - 1)
    for i in range(len(a)):
        for j in range(len(b)):
            result[i + j] ^= GaloisField.mul(a[i], b[j])
    return result


def mod_polys(dividend, divisor):
    result = list(dividend)
    while len(result) >= len(divisor):
        if result[0] != 0:
            coef = result[0]
            for i in range(len(divisor)):
                result[i] ^= GaloisField.mul(coef, divisor[i])
        result = result[1:]
    return result


def generate_generator_poly_v0(nsym):
    """从 α^0 开始"""
    g = [1]
    for i in range(nsym):
        g = multiply_polys(g, [1, GaloisField.EXP_TABLE[i]])
    return g


def generate_generator_poly_v1(nsym):
    """从 α^1 开始"""
    g = [1]
    for i in range(1, nsym + 1):
        g = multiply_polys(g, [1, GaloisField.EXP_TABLE[i]])
    return g


def encode_v0(data, nsym):
    g = generate_generator_poly_v0(nsym)
    padded = data + [0] * nsym
    return mod_polys(padded, g)


def encode_v1(data, nsym):
    g = generate_generator_poly_v1(nsym)
    padded = data + [0] * nsym
    return mod_polys(padded, g)


def main():
    # 测试数据：版本1-L，4字节数据
    data = [0x40, 0x41, 0x23, 0x45, 0x67, 0x80, 0xec, 0x11, 0xec, 0x11, 
            0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec]  # 19字节
    nsym = 7
    
    print(f"数据 ({len(data)} 字节):")
    print(f"  {[hex(b) for b in data]}")
    
    print(f"\nEC码字数: {nsym}")
    
    # v0: 从 α^0 开始
    ec0 = encode_v0(data, nsym)
    print(f"\nv0 (α^0 开始) EC码字:")
    print(f"  {[hex(b) for b in ec0]}")
    
    # v1: 从 α^1 开始
    ec1 = encode_v1(data, nsym)
    print(f"\nv1 (α^1 开始) EC码字:")
    print(f"  {[hex(b) for b in ec1]}")
    
    # 标准库的结果（之前提取的）
    std_ec = [0x14, 0x55, 0x0d, 0x29, 0x9f, 0xe9]  # 只有前6个，第7个未知
    print(f"\n标准库EC码字（前6个）:")
    print(f"  {[hex(b) for b in std_ec]}")
    
    # 对比
    print(f"\n对比:")
    print(f"  v0 vs 标准: {ec0[:len(std_ec)] == std_ec}")
    print(f"  v1 vs 标准: {ec1[:len(std_ec)] == std_ec}")
    
    # 再用标准库验证一下
    print(f"\n--- 用标准库直接验证 ---")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, 
                       box_size=1, border=0, mask_pattern=0)
    qr.add_data(bytes([0x12, 0x34, 0x56, 0x78]))
    qr.make(fit=True)
    
    # 直接访问内部数据
    print(f"标准库内部数据:")
    print(f"  数据列表: {qr.data_list}")
    print(f"  数据缓存长度: {len(qr.data_cache)}")
    print(f"  数据缓存: {[hex(b) for b in qr.data_cache]}")


if __name__ == '__main__':
    main()
