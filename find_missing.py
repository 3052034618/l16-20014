#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
找出蛇形遍历漏掉的数据模块
"""

from qrcode_generator import QRMatrix, EC_LEVEL_L


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
    version = 1
    ec_level = EC_LEVEL_L
    
    m = QRMatrix(version)
    m.place_function_patterns(ec_level, 0)
    
    s = m.size
    
    # 所有数据模块
    all_data = set()
    for r in range(s):
        for c in range(s):
            if not m.is_function[r][c]:
                all_data.add((r, c))
    
    print(f"总数据模块: {len(all_data)}")
    
    # 蛇形遍历的数据模块
    snake_data = set(list_data_modules_in_order(m.is_function, s))
    print(f"蛇形遍历: {len(snake_data)}")
    
    # 漏掉的
    missing = all_data - snake_data
    print(f"\n漏掉的模块 ({len(missing)} 个:")
    for r, c in sorted(missing):
        print(f"  ({r}, {c})")
    
    # 多出来的
    extra = snake_data - all_data
    if extra:
        print(f"\n多出来的模块 ({len(extra)} 个:")
        for r, c in sorted(extra):
            print(f"  ({r}, {c})")


if __name__ == '__main__':
    main()
