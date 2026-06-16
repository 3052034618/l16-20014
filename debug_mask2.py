#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试掩码评分：验证test模式的影响
"""

import qrcode
from qrcode.util import lost_point


def main():
    data = b"Hello, World!"
    version = 1
    ec = qrcode.constants.ERROR_CORRECT_L
    
    print(f"测试: Hello World v1-L")
    
    # 1. best_mask_pattern 的结果
    qr = qrcode.QRCode(version=version, error_correction=ec, box_size=1, border=0)
    qr.add_data(data)
    qr.make(fit=False)
    print(f"\nbest_mask_pattern() 返回: {qr.best_mask_pattern()}")
    
    # 2. 直接用 lost_point 评最终矩阵（带格式信息）
    print(f"\n最终矩阵（带格式信息）的 lost_point 评分:")
    scores_final = []
    for mask in range(8):
        qr2 = qrcode.QRCode(version=version, error_correction=ec, box_size=1, border=0, mask_pattern=mask)
        qr2.add_data(data)
        qr2.make(fit=False)
        mat = [[bool(v) for v in row] for row in qr2.get_matrix()]
        score = lost_point(mat)
        scores_final.append(score)
        print(f"  掩码 {mask}: {score}")
    best_final = min(range(8), key=lambda i: scores_final[i])
    print(f"  最佳: {best_final}")
    
    # 3. 看看 makeImpl(True, mask) 的矩阵评分
    print(f"\ntest模式（格式信息全白）的 lost_point 评分:")
    scores_test = []
    for mask in range(8):
        qr3 = qrcode.QRCode(version=version, error_correction=ec, box_size=1, border=0)
        qr3.add_data(data)
        qr3.best_fit()  # 确保版本正确
        qr3.makeImpl(True, mask)
        mat = [[bool(v) if v is not None else False for v in row] for row in qr3.modules]
        score = lost_point(mat)
        scores_test.append(score)
        print(f"  掩码 {mask}: {score}")
    best_test = min(range(8), key=lambda i: scores_test[i])
    print(f"  最佳: {best_test}")
    
    # 4. 对比差异
    print(f"\n--- 对比 ---")
    print(f"best_mask_pattern: {qr.best_mask_pattern()}")
    print(f"test模式最佳: {best_test}")
    print(f"最终矩阵最佳: {best_final}")


if __name__ == '__main__':
    main()
