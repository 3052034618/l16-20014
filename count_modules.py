#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计功能模块和数据模块数量
"""

from qrcode_generator import QRMatrix, EC_LEVEL_L


def main():
    version = 1
    ec_level = EC_LEVEL_L
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, 0)
    
    s = m.size
    print(f"版本 {version}, 大小 {s}x{s} = {s*s} 模块")
    
    func_count = 0
    data_count = 0
    for r in range(s):
        for c in range(s):
            if m.is_function[r][c]:
                func_count += 1
            else:
                data_count += 1
    
    print(f"功能模块: {func_count}")
    print(f"数据模块: {data_count}")
    print(f"总计: {func_count + data_count}")
    
    # 标准应该有多少数据模块
    # 版本1-L: 19数据 + 7EC = 26字节 = 208位
    print(f"\n标准数据位数: 26字节 * 8 = 208")
    print(f"差异: {208 - data_count}")
    
    # 找出哪些位置我们标记为功能但可能应该是数据
    print(f"\n检查格式信息周围:")
    # 行8
    print("行8:")
    for c in range(s):
        if m.is_function[8][c]:
            val = 'F' if m.modules[8][c] is None else ('1' if m.modules[8][c] else '0')
        else:
            val = 'D' if m.modules[8][c] is None else ('1' if m.modules[8][c] else '0')
        print(f"  列{c}: {val}", end="")
        if c % 10 == 9:
            print()
    print()
    
    # 列8
    print("\n列8:")
    for r in range(s):
        if m.is_function[r][8]:
            val = 'F' if m.modules[r][8] is None else ('1' if m.modules[r][8] else '0')
        else:
            val = 'D' if m.modules[r][8] is None else ('1' if m.modules[r][8] else '0')
        print(f"  行{r}: {val}", end="")
        if r % 10 == 9:
            print()
    print()
    
    # 检查暗模块
    dark_r = 4 * version + 9
    print(f"\n暗模块位置: ({dark_r}, 8)")
    print(f"  is_function: {m.is_function[dark_r][8]}")
    print(f"  value: {m.modules[dark_r][8]}")
    
    # 对比一下：行6和列6的定时图案
    print(f"\n行6定时图案:")
    for c in range(s):
        if m.is_function[6][c]:
            print(f"  列{c}: T", end="")
        if c % 10 == 9:
            print()
    print()
    
    print(f"\n列6定时图案:")
    for r in range(s):
        if m.is_function[r][6]:
            print(f"  行{r}: T", end="")
        if r % 10 == 9:
            print()
    print()


if __name__ == '__main__':
    main()
