#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查大版本二维码的定位图案
"""

from qrcode_generator import QRCodeGenerator, EC_LEVEL_M, EC_LEVEL_L

# 先测试小版本
print("=== 版本3 (小版本) ===")
text = "测试"
matrix = QRCodeGenerator.generate(text, ec_level=EC_LEVEL_M, output_format='matrix')
size = len(matrix)
version = (size - 17) // 4
print(f"版本: {version}, 尺寸: {size}x{size}")
print()

print("左上角前8行前8列:")
for r in range(8):
    row = []
    for c in range(8):
        row.append("█" if matrix[r][c] else "·")
    print("  " + "".join(row))

print()
print("=== 版本31 (大版本) ===")

# 生成一个大一点的
text = "测试大版本二维码" * 50
matrix = QRCodeGenerator.generate(text, ec_level=EC_LEVEL_M, output_format='matrix')
size = len(matrix)
version = (size - 17) // 4

print(f"版本: {version}, 尺寸: {size}x{size}")
print()

# 检查左上角
print("左上角定位图案 (前8行前8列):")
for r in range(8):
    row = []
    for c in range(8):
        row.append("█" if matrix[r][c] else "·")
    print("  " + "".join(row))

# 检查右上角
print("\n右上角定位图案 (前8行后8列):")
for r in range(8):
    row = []
    for c in range(size-8, size):
        row.append("█" if matrix[r][c] else "·")
    print("  " + "".join(row))

# 检查左下角
print("\n左下角定位图案 (后8行前8列):")
for r in range(size-8, size):
    row = []
    for c in range(8):
        row.append("█" if matrix[r][c] else "·")
    print("  " + "".join(row))

# 简单检查
print(f"\n左上角 (0,0): {matrix[0][0]}")
print(f"右上角 (0,{size-1}): {matrix[0][size-1]}")
print(f"左下角 ({size-1},0): {matrix[size-1][0]}")
