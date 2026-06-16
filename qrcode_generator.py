#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二维码生成器完整实现（符合 ISO/IEC 18004 标准）
包含：数据编码(字节模式)、里德-所罗门纠错、矩阵布局、掩码选择、SVG/点阵渲染
"""

import math
from typing import List, Tuple, Optional

# ============================================================
# 第一部分：GF(256) 有限域运算 + 里德-所罗门纠错码
# ============================================================

class GaloisField:
    """GF(256) 有限域，使用本原多项式 x^8 + x^4 + x^3 + x^2 + 1 (0x11d)"""
    
    EXP_TABLE = [0] * 512
    LOG_TABLE = [0] * 256
    
    @staticmethod
    def _init_tables():
        x = 1
        for i in range(255):
            GaloisField.EXP_TABLE[i] = x
            GaloisField.LOG_TABLE[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11d
        for i in range(255, 512):
            GaloisField.EXP_TABLE[i] = GaloisField.EXP_TABLE[i - 255]
    
    @staticmethod
    def add(a: int, b: int) -> int:
        return a ^ b
    
    @staticmethod
    def mul(a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return GaloisField.EXP_TABLE[GaloisField.LOG_TABLE[a] + GaloisField.LOG_TABLE[b]]
    
    @staticmethod
    def div(a: int, b: int) -> int:
        if b == 0:
            raise ZeroDivisionError()
        if a == 0:
            return 0
        return GaloisField.EXP_TABLE[(GaloisField.LOG_TABLE[a] - GaloisField.LOG_TABLE[b]) % 255]

GaloisField._init_tables()


class ReedSolomon:
    """里德-所罗门编码器"""
    
    @staticmethod
    def multiply_polys(a: List[int], b: List[int]) -> List[int]:
        result = [0] * (len(a) + len(b) - 1)
        for i in range(len(a)):
            for j in range(len(b)):
                result[i + j] = GaloisField.add(result[i + j], GaloisField.mul(a[i], b[j]))
        return result
    
    @staticmethod
    def mod_polys(dividend: List[int], divisor: List[int]) -> List[int]:
        result = list(dividend)
        while len(result) >= len(divisor):
            if result[0] != 0:
                coef = result[0]
                for i in range(len(divisor)):
                    result[i] = GaloisField.add(result[i], GaloisField.mul(coef, divisor[i]))
            result = result[1:]
        return result
    
    @staticmethod
    def generate_generator_poly(nsym: int) -> List[int]:
        g = [1]
        for i in range(nsym):
            g = ReedSolomon.multiply_polys(g, [1, GaloisField.EXP_TABLE[i]])
        return g
    
    @staticmethod
    def encode(data: List[int], nsym: int) -> List[int]:
        g = ReedSolomon.generate_generator_poly(nsym)
        padded = data + [0] * nsym
        remainder = ReedSolomon.mod_polys(padded, g)
        return remainder


# ============================================================
# 第二部分：QR码标准常量（完整版本1-40）
# ============================================================

EC_LEVEL_L = 0
EC_LEVEL_M = 1
EC_LEVEL_Q = 2
EC_LEVEL_H = 3

EC_LEVEL_NAMES = {EC_LEVEL_L: 'L', EC_LEVEL_M: 'M', EC_LEVEL_Q: 'Q', EC_LEVEL_H: 'H'}
MODE_BYTE = 0b0100

# 完整版本1-40的容量表
# 格式: version -> [L, M, Q, H] -> (total_data, ec_per_block, nb1, dp1, nb2, dp2)
FULL_CAPACITY_DATA = {
    1:  [(19, 7, 1, 19, 0, 0), (16, 10, 1, 16, 0, 0), (13, 13, 1, 13, 0, 0), (9, 17, 1, 9, 0, 0)],
    2:  [(34, 10, 1, 34, 0, 0), (28, 16, 1, 28, 0, 0), (22, 22, 1, 22, 0, 0), (16, 28, 1, 16, 0, 0)],
    3:  [(55, 15, 1, 55, 0, 0), (44, 26, 1, 44, 0, 0), (34, 18, 2, 17, 0, 0), (26, 22, 2, 13, 0, 0)],
    4:  [(80, 20, 1, 80, 0, 0), (64, 18, 2, 32, 0, 0), (48, 26, 2, 24, 0, 0), (36, 16, 4, 9, 0, 0)],
    5:  [(108, 26, 1, 108, 0, 0), (86, 24, 2, 43, 0, 0), (62, 18, 2, 15, 2, 16), (46, 22, 2, 11, 2, 12)],
    6:  [(136, 18, 2, 68, 0, 0), (108, 16, 4, 27, 0, 0), (76, 24, 4, 19, 0, 0), (60, 28, 4, 15, 0, 0)],
    7:  [(156, 20, 2, 78, 0, 0), (124, 18, 4, 31, 0, 0), (88, 18, 2, 14, 4, 15), (66, 26, 4, 13, 1, 14)],
    8:  [(194, 24, 2, 97, 0, 0), (154, 22, 2, 38, 2, 39), (110, 22, 4, 18, 2, 19), (86, 26, 4, 14, 2, 15)],
    9:  [(232, 30, 2, 116, 0, 0), (182, 22, 3, 36, 2, 37), (132, 20, 4, 16, 4, 17), (100, 24, 4, 12, 4, 13)],
    10: [(274, 18, 2, 68, 2, 69), (216, 26, 4, 43, 1, 44), (154, 24, 6, 19, 2, 20), (122, 28, 6, 15, 2, 16)],
    11: [(324, 20, 4, 81, 0, 0), (254, 30, 1, 50, 4, 51), (180, 28, 4, 22, 4, 23), (140, 24, 3, 12, 8, 13)],
    12: [(370, 24, 2, 92, 2, 93), (290, 22, 6, 36, 2, 37), (210, 26, 4, 20, 6, 21), (158, 28, 7, 14, 4, 15)],
    13: [(428, 26, 4, 107, 0, 0), (334, 22, 8, 37, 1, 38), (258, 24, 8, 20, 4, 21), (180, 22, 12, 11, 4, 12)],
    14: [(461, 30, 3, 115, 1, 116), (365, 24, 4, 40, 5, 41), (292, 20, 11, 16, 5, 17), (197, 24, 11, 12, 5, 13)],
    15: [(523, 22, 5, 87, 1, 88), (415, 24, 5, 41, 5, 42), (328, 30, 5, 24, 7, 25), (223, 24, 11, 12, 7, 13)],
    16: [(589, 24, 5, 98, 1, 99), (453, 28, 7, 45, 3, 46), (376, 24, 15, 19, 2, 20), (253, 30, 3, 15, 13, 16)],
    17: [(647, 28, 1, 107, 5, 108), (507, 28, 10, 46, 1, 47), (426, 28, 1, 22, 15, 23), (283, 28, 2, 14, 17, 15)],
    18: [(721, 30, 5, 120, 1, 121), (563, 26, 9, 43, 4, 44), (470, 28, 17, 22, 1, 23), (313, 28, 2, 14, 19, 15)],
    19: [(795, 28, 3, 113, 4, 114), (627, 26, 3, 44, 11, 45), (531, 26, 17, 21, 4, 22), (341, 26, 9, 13, 16, 14)],
    20: [(861, 28, 3, 107, 5, 108), (669, 26, 3, 41, 13, 42), (574, 30, 15, 24, 5, 25), (385, 28, 15, 15, 10, 16)],
    21: [(932, 28, 4, 116, 4, 117), (714, 26, 17, 42, 0, 0), (628, 28, 17, 22, 6, 23), (406, 26, 19, 13, 6, 14)],
    22: [(1006, 28, 2, 111, 7, 112), (782, 28, 17, 46, 0, 0), (669, 28, 7, 24, 16, 25), (442, 28, 34, 14, 0, 0)],
    23: [(1094, 30, 4, 121, 5, 122), (860, 28, 4, 47, 14, 48), (714, 28, 11, 24, 14, 25), (474, 28, 16, 14, 14, 15)],
    24: [(1174, 30, 6, 117, 4, 118), (914, 28, 6, 45, 14, 46), (782, 28, 11, 24, 16, 25), (509, 28, 30, 14, 2, 15)],
    25: [(1276, 26, 8, 106, 4, 107), (1000, 28, 8, 47, 13, 48), (860, 28, 7, 24, 22, 25), (565, 28, 22, 14, 13, 15)],
    26: [(1370, 28, 10, 114, 2, 115), (1062, 28, 19, 46, 4, 47), (914, 28, 28, 24, 6, 25), (590, 28, 33, 14, 4, 15)],
    27: [(1468, 30, 8, 122, 4, 123), (1128, 28, 22, 45, 3, 46), (1000, 28, 8, 23, 26, 24), (652, 28, 12, 15, 28, 16)],
    28: [(1531, 30, 3, 117, 10, 118), (1193, 28, 3, 45, 23, 46), (1062, 28, 4, 24, 31, 25), (674, 28, 11, 15, 31, 16)],
    29: [(1631, 30, 7, 116, 6, 117), (1267, 28, 21, 45, 7, 46), (1128, 28, 1, 23, 37, 24), (721, 28, 19, 15, 26, 16)],
    30: [(1735, 30, 5, 115, 8, 116), (1373, 28, 19, 47, 10, 48), (1193, 28, 15, 24, 25, 25), (757, 28, 23, 15, 25, 16)],
    31: [(1843, 30, 13, 115, 3, 116), (1455, 28, 2, 46, 29, 47), (1267, 28, 42, 24, 1, 25), (789, 28, 23, 15, 28, 16)],
    32: [(1955, 30, 17, 115, 0, 0), (1541, 28, 10, 46, 23, 47), (1373, 28, 10, 24, 35, 25), (821, 28, 19, 15, 35, 16)],
    33: [(2071, 30, 17, 115, 1, 116), (1631, 28, 14, 46, 21, 47), (1455, 28, 29, 24, 19, 25), (883, 28, 11, 15, 46, 16)],
    34: [(2191, 30, 13, 115, 6, 116), (1725, 28, 14, 46, 23, 47), (1541, 28, 44, 24, 7, 25), (915, 28, 59, 16, 1, 17)],
    35: [(2306, 30, 12, 121, 7, 122), (1812, 28, 12, 47, 26, 48), (1631, 28, 39, 24, 14, 25), (963, 28, 22, 15, 41, 16)],
    36: [(2434, 30, 6, 121, 14, 122), (1914, 28, 6, 47, 34, 48), (1725, 28, 46, 24, 10, 25), (1005, 28, 2, 16, 64, 17)],
    37: [(2566, 30, 17, 122, 4, 123), (1992, 28, 29, 46, 14, 47), (1812, 28, 49, 24, 10, 25), (1053, 28, 24, 15, 46, 16)],
    38: [(2702, 30, 4, 122, 18, 123), (2102, 28, 13, 46, 32, 47), (1914, 28, 48, 24, 14, 25), (1095, 28, 42, 15, 32, 16)],
    39: [(2812, 30, 20, 117, 4, 118), (2216, 28, 40, 47, 7, 48), (1992, 28, 43, 24, 22, 25), (1139, 28, 10, 15, 67, 16)],
    40: [(2953, 30, 19, 118, 6, 119), (2334, 28, 18, 47, 31, 48), (2102, 28, 34, 24, 34, 25), (1219, 30, 20, 16, 61, 17)],
}

QR_CAPACITY_TABLE = {EC_LEVEL_L: {}, EC_LEVEL_M: {}, EC_LEVEL_Q: {}, EC_LEVEL_H: {}}

def _init_capacity_table():
    for version, levels in FULL_CAPACITY_DATA.items():
        for ec_level, (total_data, ec_per_block, nb1, dp1, nb2, dp2) in enumerate(levels):
            QR_CAPACITY_TABLE[ec_level][version] = {
                'total_data_codewords': total_data,
                'ec_per_block': ec_per_block,
                'num_blocks_g1': nb1,
                'data_per_block_g1': dp1,
                'num_blocks_g2': nb2,
                'data_per_block_g2': dp2,
            }

_init_capacity_table()

# 完整的对齐图案位置表（版本1-40）
ALIGNMENT_PATTERN_POSITIONS = {
    1:  [],
    2:  [6, 18],
    3:  [6, 22],
    4:  [6, 26],
    5:  [6, 30],
    6:  [6, 34],
    7:  [6, 22, 38],
    8:  [6, 24, 42],
    9:  [6, 26, 46],
    10: [6, 28, 50],
    11: [6, 30, 54],
    12: [6, 32, 58],
    13: [6, 34, 62],
    14: [6, 26, 46, 66],
    15: [6, 26, 48, 70],
    16: [6, 26, 50, 74],
    17: [6, 30, 54, 78],
    18: [6, 30, 56, 82],
    19: [6, 30, 58, 86],
    20: [6, 34, 62, 90],
    21: [6, 28, 50, 72, 94],
    22: [6, 26, 50, 74, 98],
    23: [6, 30, 54, 78, 102],
    24: [6, 28, 54, 80, 106],
    25: [6, 32, 58, 84, 110],
    26: [6, 30, 58, 86, 114],
    27: [6, 34, 62, 90, 118],
    28: [6, 26, 50, 74, 98, 122],
    29: [6, 30, 54, 78, 102, 126],
    30: [6, 26, 52, 78, 104, 130],
    31: [6, 30, 56, 82, 108, 134],
    32: [6, 34, 60, 86, 112, 138],
    33: [6, 30, 58, 86, 114, 142],
    34: [6, 34, 62, 90, 118, 146],
    35: [6, 30, 54, 78, 102, 126, 150],
    36: [6, 24, 50, 76, 102, 128, 154],
    37: [6, 28, 54, 80, 106, 132, 158],
    38: [6, 32, 58, 84, 110, 136, 162],
    39: [6, 26, 54, 82, 110, 138, 166],
    40: [6, 30, 58, 86, 114, 142, 170],
}

# 完整的余位数表（版本1-40）
REMAINDER_BITS = {
    1: 0,  2: 7,  3: 7,  4: 7,  5: 7,  6: 7,  7: 0,  8: 0,
    9: 0,  10: 0, 11: 0, 12: 0, 13: 0, 14: 3, 15: 3, 16: 3,
    17: 3, 18: 3, 19: 3, 20: 3, 21: 4, 22: 4, 23: 4, 24: 4,
    25: 4, 26: 4, 27: 4, 28: 3, 29: 3, 30: 3, 31: 3, 32: 3,
    33: 3, 34: 3, 35: 0,  36: 0, 37: 0, 38: 0, 39: 0, 40: 0,
}

# 格式信息 BCH 码生成多项式 (x^10 + x^8 + x^5 + x^4 + x^2 + x + 1)
FORMAT_INFO_GEN_POLY = 0b10100110111
FORMAT_INFO_MASK = 0b101010000010010

# 版本信息 BCH 码生成多项式 (x^12 + x^11 + x^10 + x^9 + x^8 + x^5 + x^2 + 1)
VERSION_INFO_GEN_POLY = 0b1111100100101


# ============================================================
# 第三部分：数据编码与分块
# ============================================================

class DataEncoder:
    """数据编码器：字节模式"""
    
    @staticmethod
    def encode_byte_mode(text: str) -> Tuple[List[int], int]:
        data_bytes = text.encode('utf-8')
        char_count = len(data_bytes)
        bits = [0, 1, 0, 0]  # 模式指示符: 0100
        # 字符数指示符先用16位占位，版本确定后调整
        cc_bits = format(char_count, '016b')
        bits.extend([int(b) for b in cc_bits])
        # 数据字节
        for byte in data_bytes:
            bits.extend([int(b) for b in format(byte, '08b')])
        return bits, char_count
    
    @staticmethod
    def adjust_char_count_indicator(bits: List[int], char_count: int, version: int) -> List[int]:
        cc_len = 8 if version <= 9 else 16
        cc_bits = format(char_count, '0' + str(cc_len) + 'b')
        # bits[0:4] 是模式指示符, bits[4:20] 是原16位字符数
        return bits[:4] + [int(b) for b in cc_bits] + bits[20:]
    
    @staticmethod
    def pad_bits(bits: List[int], total_data_bits: int) -> List[int]:
        result = list(bits)
        # 1. 终止符：最多4个0
        term_len = min(4, total_data_bits - len(result))
        result.extend([0] * term_len)
        # 2. 补0对齐到字节
        while len(result) % 8 != 0 and len(result) < total_data_bits:
            result.append(0)
        # 3. 交替填充 0xEC 和 0x11
        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        while len(result) < total_data_bits:
            byte = pad_bytes[pad_idx % 2]
            pad_idx += 1
            result.extend([int(b) for b in format(byte, '08b')])
        return result[:total_data_bits]
    
    @staticmethod
    def bits_to_bytes(bits: List[int]) -> List[int]:
        result = []
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                if i + j < len(bits):
                    byte = (byte << 1) | bits[i + j]
            result.append(byte)
        return result
    
    @staticmethod
    def split_into_blocks(data_codewords: List[int], ec_level: int, version: int) -> Tuple[List[List[int]], int]:
        cap = QR_CAPACITY_TABLE[ec_level][version]
        ec_per_block = cap['ec_per_block']
        nb1, dp1 = cap['num_blocks_g1'], cap['data_per_block_g1']
        nb2, dp2 = cap['num_blocks_g2'], cap['data_per_block_g2']
        
        blocks = []
        idx = 0
        for _ in range(nb1):
            blocks.append(data_codewords[idx:idx + dp1])
            idx += dp1
        for _ in range(nb2):
            blocks.append(data_codewords[idx:idx + dp2])
            idx += dp2
        return blocks, ec_per_block
    
    @staticmethod
    def interleave(blocks: List[List[int]]) -> List[int]:
        """交织码字：轮流从每块取一个"""
        if not blocks:
            return []
        max_len = max(len(b) for b in blocks)
        result = []
        for i in range(max_len):
            for block in blocks:
                if i < len(block):
                    result.append(block[i])
        return result
    
    @staticmethod
    def build_final_bitstream(data_codewords: List[int], ec_codewords: List[int], remainder: int) -> List[int]:
        bits = []
        for b in data_codewords:
            bits.extend([int(x) for x in format(b, '08b')])
        for b in ec_codewords:
            bits.extend([int(x) for x in format(b, '08b')])
        bits.extend([0] * remainder)
        return bits


# ============================================================
# 第四部分：QR 码矩阵构建
# ============================================================

class QRMatrix:
    """QR 码矩阵"""
    
    def __init__(self, version: int):
        self.version = version
        self.size = 17 + version * 4
        self.modules = [[None] * self.size for _ in range(self.size)]
        self.is_function = [[False] * self.size for _ in range(self.size)]
    
    def set_module(self, row: int, col: int, value: bool, is_function: bool = False):
        if 0 <= row < self.size and 0 <= col < self.size:
            self.modules[row][col] = value
            if is_function:
                self.is_function[row][col] = True
    
    def place_finder_pattern(self, center_r: int, center_c: int):
        """放置7x7定位图案：深-浅-深 三层方框"""
        for r in range(-3, 4):
            for c in range(-3, 4):
                nr, nc = center_r + r, center_c + c
                if abs(r) == 3 or abs(c) == 3 or (abs(r) <= 1 and abs(c) <= 1):
                    self.set_module(nr, nc, True, is_function=True)
                else:
                    self.set_module(nr, nc, False, is_function=True)
    
    def place_separator(self):
        """定位图案周围的8x8白色分隔符"""
        s = self.size
        for i in range(8):
            # 左上角
            self.set_module(i, 7, False, is_function=True)
            self.set_module(7, i, False, is_function=True)
            # 右上角
            self.set_module(i, s - 8, False, is_function=True)
            self.set_module(7, s - 8 + i, False, is_function=True)
            # 左下角
            self.set_module(s - 8, i, False, is_function=True)
            self.set_module(s - 8 + i, 7, False, is_function=True)
    
    def place_alignment_pattern(self, center_r: int, center_c: int):
        """放置5x5对齐图案：深-浅-深"""
        # 跳过与三个定位图案重叠的位置
        if (center_r <= 7 and center_c <= 7) or \
           (center_r <= 7 and center_c >= self.size - 8) or \
           (center_r >= self.size - 8 and center_c <= 7):
            return
        for r in range(-2, 3):
            for c in range(-2, 3):
                nr, nc = center_r + r, center_c + c
                if abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0):
                    self.set_module(nr, nc, True, is_function=True)
                else:
                    self.set_module(nr, nc, False, is_function=True)
    
    def place_timing_patterns(self):
        """第6行和第6列的交替黑白定时图案"""
        for i in range(8, self.size - 8):
            val = (i % 2 == 0)
            self.set_module(6, i, val, is_function=True)
            self.set_module(i, 6, val, is_function=True)
    
    def place_dark_module(self):
        """固定位置的深色模块"""
        r = 4 * self.version + 9
        self.set_module(r, 8, True, is_function=True)
    
    def _encode_format_info(self, ec_level: int, mask_num: int) -> int:
        """
        标准格式信息编码：
        5位数据（2位EC等级 + 3位掩码）+ 10位BCH纠错 + 异或掩码
        """
        ec_codes = {EC_LEVEL_L: 0b01, EC_LEVEL_M: 0b00, EC_LEVEL_Q: 0b11, EC_LEVEL_H: 0b10}
        data = (ec_codes[ec_level] << 3) | mask_num  # 5位数据
        
        # BCH(15,5) 编码：计算 10 位纠错码
        d = data << 10
        gen = FORMAT_INFO_GEN_POLY  # 11位 (bit 10 到 bit 0)
        
        for i in range(4, -1, -1):
            if (d >> (i + 10)) & 1:
                d ^= gen << i
        
        # 组合后与掩码异或
        result = ((data << 10) | (d & 0x3FF)) ^ FORMAT_INFO_MASK
        return result
    
    def _encode_version_info(self, version: int) -> int:
        """
        标准版本信息编码：
        6位版本号 + 12位BCH纠错
        """
        v = version << 12
        gen = VERSION_INFO_GEN_POLY  # 13位
        
        for i in range(5, -1, -1):
            if (v >> (i + 12)) & 1:
                v ^= gen << i
        
        return (version << 12) | (v & 0xFFF)
    
    def place_format_info(self, format_data: int):
        """
        标准格式信息放置：15位，两处冗余位置
        位顺序：从 MSB 到 LSB，即 bit14 到 bit0
        """
        bits = [(format_data >> i) & 1 for i in range(14, -1, -1)]
        s = self.size
        
        # 位置1：围绕左上角定位图案
        # 行8，列0-5, 7-8
        pos1 = [
            (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
            (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
        ]
        for i, (r, c) in enumerate(pos1):
            self.set_module(r, c, bool(bits[i]), is_function=True)
        
        # 位置2：右下角区域的两部分
        # 行 size-1 到 size-7，列8
        pos2_part1 = [
            (s - 1, 8), (s - 2, 8), (s - 3, 8), (s - 4, 8), (s - 5, 8), (s - 6, 8), (s - 7, 8),
        ]
        # 行8，列 size-8 到 size-1
        pos2_part2 = [
            (8, s - 8), (8, s - 7), (8, s - 6), (8, s - 5),
            (8, s - 4), (8, s - 3), (8, s - 2), (8, s - 1),
        ]
        pos2 = pos2_part1 + pos2_part2
        for i, (r, c) in enumerate(pos2):
            self.set_module(r, c, bool(bits[i]), is_function=True)
    
    def place_version_info(self, version_data: int):
        """
        标准版本信息放置：18位，版本>=7时需要
        位顺序：从 MSB 到 LSB
        """
        bits = [(version_data >> i) & 1 for i in range(17, -1, -1)]
        s = self.size
        
        # 位置1：右上角区域：行 size-11 到 size-9，列0-5
        # 按列优先排列
        idx = 0
        for col in range(6):
            for row in range(s - 11, s - 8):
                self.set_module(row, col, bool(bits[idx]), is_function=True)
                idx += 1
        
        # 位置2：左下角区域：行0-5，列 size-11 到 size-9
        # 按行优先排列
        idx = 0
        for row in range(6):
            for col in range(s - 11, s - 8):
                self.set_module(row, col, bool(bits[idx]), is_function=True)
                idx += 1
    
    def place_function_patterns(self, ec_level: int, mask_num: int):
        """放置所有功能图案"""
        # 1. 三个定位图案
        s = self.size
        self.place_finder_pattern(3, 3)
        self.place_finder_pattern(3, s - 4)
        self.place_finder_pattern(s - 4, 3)
        
        # 2. 分隔符
        self.place_separator()
        
        # 3. 对齐图案
        if self.version >= 2:
            positions = ALIGNMENT_PATTERN_POSITIONS.get(self.version, [])
            for r in positions:
                for c in positions:
                    self.place_alignment_pattern(r, c)
        
        # 4. 定时图案
        self.place_timing_patterns()
        
        # 5. 深色模块
        self.place_dark_module()
        
        # 6. 格式信息
        fmt = self._encode_format_info(ec_level, mask_num)
        self.place_format_info(fmt)
        
        # 7. 版本信息（>=7）
        if self.version >= 7:
            ver = self._encode_version_info(self.version)
            self.place_version_info(ver)
    
    def place_data(self, data_bits: List[int]):
        """
        标准数据放置顺序：蛇形填充
        - 从右下角开始，每次处理两列
        - 跳过第6列（定时图案）
        - 方向交替：向上、向下、向上...
        - 在两列中：先右列（从下到上或上到下），再左列
        """
        bit_idx = 0
        total_bits = len(data_bits)
        s = self.size
        
        # 从最右边开始，每次处理两列，向左移动
        col_pair = 0
        while True:
            # 当前处理的两列：右列 = s-1 - col_pair*2, 左列 = 右列 - 1
            right_col = s - 1 - col_pair * 2
            
            # 如果右列 <= 0，完成
            if right_col <= 0:
                break
            
            # 跳过第6列（如果右列是7，则左列是6，需要跳过整对）
            left_col = right_col - 1
            if left_col == 6:
                # 调整：左列改为5（跳过列6）
                left_col = 5
            
            # 确定方向：第0对（最右）向上，第1对向下，第2对向上，依此类推
            upward = (col_pair % 2 == 0)
            
            if upward:
                rows = range(s - 1, -1, -1)
            else:
                rows = range(s)
            
            # 放置顺序：先右列，再左列
            for row in rows:
                for c in [right_col, left_col]:
                    if bit_idx >= total_bits:
                        return
                    if not self.is_function[row][c] and self.modules[row][c] is None:
                        self.set_module(row, c, bool(data_bits[bit_idx]))
                        bit_idx += 1
            
            col_pair += 1


# ============================================================
# 第五部分：掩码算法与惩罚评分（标准实现）
# ============================================================

class Masker:
    """8种数据掩码算法 + 标准惩罚评分"""
    
    @staticmethod
    def mask_function(mask_num: int, row: int, col: int) -> bool:
        """8种标准掩码函数：返回True表示翻转"""
        if mask_num == 0:
            return (row + col) % 2 == 0
        elif mask_num == 1:
            return row % 2 == 0
        elif mask_num == 2:
            return col % 3 == 0
        elif mask_num == 3:
            return (row + col) % 3 == 0
        elif mask_num == 4:
            return ((row // 2) + (col // 3)) % 2 == 0
        elif mask_num == 5:
            return ((row * col) % 2 + (row * col) % 3) == 0
        elif mask_num == 6:
            return (((row * col) % 2 + (row * col) % 3) % 2) == 0
        elif mask_num == 7:
            return (((row + col) % 2 + (row * col) % 3) % 2) == 0
        raise ValueError(f"Invalid mask: {mask_num}")
    
    @staticmethod
    def apply_mask(matrix: QRMatrix, mask_num: int):
        for r in range(matrix.size):
            for c in range(matrix.size):
                if not matrix.is_function[r][c] and matrix.modules[r][c] is not None:
                    if Masker.mask_function(mask_num, r, c):
                        matrix.modules[r][c] = not matrix.modules[r][c]
    
    @staticmethod
    def apply_mask_temp(matrix: QRMatrix, mask_num: int) -> List[List[bool]]:
        result = []
        for r in range(matrix.size):
            row = []
            for c in range(matrix.size):
                v = matrix.modules[r][c]
                if not matrix.is_function[r][c] and v is not None:
                    if Masker.mask_function(mask_num, r, c):
                        v = not v
                row.append(v)
            result.append(row)
        return result
    
    @staticmethod
    def _get_runs(modules_line: List[bool]) -> List[Tuple[bool, int]]:
        """
        计算一行/列的行程长度编码（RLE）
        返回：[(颜色, 长度), ...]
        """
        if not modules_line:
            return []
        runs = []
        current = modules_line[0]
        count = 1
        for v in modules_line[1:]:
            if v == current:
                count += 1
            else:
                runs.append((current, count))
                current = v
                count = 1
        runs.append((current, count))
        return runs
    
    @staticmethod
    def _check_finder_pattern(runs: List[Tuple[bool, int]]) -> int:
        """
        标准N3检测：检查行程序列中是否有类似定位图案的 1:1:3:1:1 比例
        序列必须是：浅色(n) + 深色(1) + 浅色(1) + 深色(3) + 浅色(1) + 深色(1) + 浅色(n)
        其中浅色部分的长度至少为 1，深色部分比例为 1:1:3:1:1
        
        这是标准的N3检测方式，检测连续模块的宽度比例，而不是固定的7个模块。
        这样不会把普通的7格纹理误判为定位图案。
        """
        count = 0
        # 需要至少 5 段（深-浅-深-浅-深）才能形成 1:1:3:1:1
        for i in range(len(runs) - 4):
            # 检查5段：颜色必须是 深-浅-深-浅-深
            if runs[i][0] and not runs[i+1][0] and runs[i+2][0] and not runs[i+3][0] and runs[i+4][0]:
                # 检查比例：1:1:3:1:1
                # 取最短的深色段作为单位1
                d1, d2, d3 = runs[i][1], runs[i+2][1], runs[i+4][1]
                l1, l2 = runs[i+1][1], runs[i+3][1]
                
                # 所有深色段应该是单位长度的倍数
                # 浅色段也应该接近单位长度
                unit = min(d1, d2, d3, l1, l2)
                if unit == 0:
                    continue
                
                # 检查比例是否接近 1:1:3:1:1（允许容差）
                # 深色段：d1, d3, d4 应该 ≈ unit
                # 深色段：d3 应该 ≈ 3*unit
                # 浅色段：l1, l2 应该 ≈ unit
                tol = unit // 2  # 容差半个单位
                
                if (abs(d1 - unit) <= tol and
                    abs(l1 - unit) <= tol and
                    abs(d2 - 3 * unit) <= tol and
                    abs(l2 - unit) <= tol and
                    abs(d3 - unit) <= tol):
                    # 还需要检查两侧有足够的浅色空间（至少1个单位）
                    # 前一段（如果有）应该是浅色且长度 >= unit
                    # 后一段（如果有）应该是浅色且长度 >= unit
                    left_ok = (i == 0) or (not runs[i-1][0] and runs[i-1][1] >= unit)
                    right_ok = (i + 5 >= len(runs)) or (not runs[i+5][0] and runs[i+5][1] >= unit)
                    
                    if left_ok and right_ok:
                        count += 1
        return count
    
    @staticmethod
    def calculate_penalty(modules: List[List[bool]]) -> int:
        """
        标准四项惩罚评分（ISO/IEC 18004）
        分数越低越好
        """
        size = len(modules)
        penalty = 0
        
        # === N1: 连续5个以上同色模块 ===
        # 每连续5个 +3 分，每多1个 +1 分
        for r in range(size):
            count = 1
            for c in range(1, size):
                if modules[r][c] == modules[r][c-1]:
                    count += 1
                else:
                    if count >= 5:
                        penalty += 3 + (count - 5)
                    count = 1
            if count >= 5:
                penalty += 3 + (count - 5)
        
        for c in range(size):
            count = 1
            for r in range(1, size):
                if modules[r][c] == modules[r-1][c]:
                    count += 1
                else:
                    if count >= 5:
                        penalty += 3 + (count - 5)
                    count = 1
            if count >= 5:
                penalty += 3 + (count - 5)
        
        # === N2: 2x2 同色方块 ===
        # 每个 +3 分
        for r in range(size - 1):
            for c in range(size - 1):
                v = modules[r][c]
                if v == modules[r][c+1] == modules[r+1][c] == modules[r+1][c+1]:
                    penalty += 3
        
        # === N3: 类定位图案序列（标准RLE比例检测） ===
        # 每次出现 +40 分
        for r in range(size):
            row = [modules[r][c] for c in range(size)]
            runs = Masker._get_runs(row)
            penalty += Masker._check_finder_pattern(runs) * 40
        
        for c in range(size):
            col = [modules[r][c] for r in range(size)]
            runs = Masker._get_runs(col)
            penalty += Masker._check_finder_pattern(runs) * 40
        
        # === N4: 深色模块比例偏离50% ===
        # 每偏离5% +10 分
        dark = sum(1 for r in range(size) for c in range(size) if modules[r][c])
        total = size * size
        percent = dark * 100 / total
        # 取最接近的5%倍数，计算与50%的偏差
        k = abs(percent - 50) / 5
        penalty += int(k) * 10
        
        return penalty
    
    @staticmethod
    def select_best_mask(matrix: QRMatrix, data_bits: List[int], ec_level: int) -> int:
        """选择惩罚分数最低的掩码"""
        best_mask = 0
        best_penalty = float('inf')
        
        for mask_num in range(8):
            temp = QRMatrix(matrix.version)
            temp.place_function_patterns(ec_level, mask_num)
            temp.place_data(data_bits)
            masked = Masker.apply_mask_temp(temp, mask_num)
            # 转换为全布尔矩阵（None当作False）
            eval_mat = [[False if v is None else v for v in row] for row in masked]
            penalty = Masker.calculate_penalty(eval_mat)
            if penalty < best_penalty:
                best_penalty = penalty
                best_mask = mask_num
        
        return best_mask


# ============================================================
# 第六部分：版本选择
# ============================================================

class VersionSelector:
    
    @staticmethod
    def get_remainder_bits(version: int) -> int:
        return REMAINDER_BITS.get(version, 0)
    
    @staticmethod
    def select_version(text: str, ec_level: int) -> int:
        """根据数据量自动选择最小的版本（1-40）"""
        data_bytes = text.encode('utf-8')
        char_count = len(data_bytes)
        
        for version in range(1, 41):
            cap = QR_CAPACITY_TABLE.get(ec_level, {}).get(version)
            if cap is None:
                continue
            
            total_bits = cap['total_data_codewords'] * 8
            cc_bits = 8 if version <= 9 else 16
            needed = 4 + cc_bits + char_count * 8
            
            # 至少需要4位终止符
            if needed + 4 <= total_bits:
                return version
        
        max_cap = QR_CAPACITY_TABLE[ec_level][40]['total_data_codewords']
        raise ValueError(
            f"数据过大！当前数据需要 {char_count} 字节 + 开销，"
            f"版本40-{EC_LEVEL_NAMES[ec_level]} 最大容量 {max_cap} 字节"
        )


# ============================================================
# 第七部分：渲染
# ============================================================

class Renderer:
    
    @staticmethod
    def to_ascii(matrix: QRMatrix, quiet_zone: int = 4) -> str:
        s = matrix.size + quiet_zone * 2
        lines = []
        for r in range(s):
            line = []
            for c in range(s):
                mr, mc = r - quiet_zone, c - quiet_zone
                if 0 <= mr < matrix.size and 0 <= mc < matrix.size:
                    v = matrix.modules[mr][mc]
                    line.append('█' if v else ' ')
                else:
                    line.append(' ')
            lines.append(''.join(line))
        return '\n'.join(lines)
    
    @staticmethod
    def to_svg(matrix: QRMatrix, module_size: int = 10, quiet_zone: int = 4,
               fg: str = '#000000', bg: str = '#ffffff') -> str:
        s = matrix.size + quiet_zone * 2
        ps = s * module_size
        
        parts = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ps} {ps}" width="{ps}" height="{ps}">',
            f'  <rect width="100%" height="100%" fill="{bg}"/>',
        ]
        
        for r in range(matrix.size):
            for c in range(matrix.size):
                if matrix.modules[r][c]:
                    x = (c + quiet_zone) * module_size
                    y = (r + quiet_zone) * module_size
                    parts.append(
                        f'  <rect x="{x}" y="{y}" width="{module_size}" height="{module_size}" fill="{fg}"/>'
                    )
        
        parts.append('</svg>')
        return '\n'.join(parts)
    
    @staticmethod
    def to_boolean_matrix(matrix: QRMatrix, quiet_zone: int = 4) -> List[List[bool]]:
        s = matrix.size + quiet_zone * 2
        result = []
        for r in range(s):
            row = []
            for c in range(s):
                mr, mc = r - quiet_zone, c - quiet_zone
                if 0 <= mr < matrix.size and 0 <= mc < matrix.size:
                    row.append(bool(matrix.modules[mr][mc]))
                else:
                    row.append(False)
            result.append(row)
        return result


# ============================================================
# 第八部分：主入口
# ============================================================

class QRCodeGenerator:
    
    @staticmethod
    def generate(text: str, ec_level: int = EC_LEVEL_M, output_format: str = 'ascii',
                 force_version: Optional[int] = None):
        """
        生成标准二维码
        
        Args:
            text: 要编码的文本
            ec_level: 纠错等级 (L/M/Q/H)
            output_format: 'ascii', 'svg', 'matrix'
            force_version: 强制使用指定版本（1-40），None 为自动选择
        """
        # 1. 选择版本
        if force_version is not None:
            if not (1 <= force_version <= 40):
                raise ValueError("版本必须在1-40之间")
            version = force_version
        else:
            version = VersionSelector.select_version(text, ec_level)
        
        # 2. 数据编码
        bits, char_count = DataEncoder.encode_byte_mode(text)
        bits = DataEncoder.adjust_char_count_indicator(bits, char_count, version)
        
        # 3. 补齐比特
        cap = QR_CAPACITY_TABLE[ec_level][version]
        total_bits = cap['total_data_codewords'] * 8
        bits = DataEncoder.pad_bits(bits, total_bits)
        
        # 4. 转码字
        data_codewords = DataEncoder.bits_to_bytes(bits)
        
        # 5. 分块 + 生成纠错码
        blocks, ec_per_block = DataEncoder.split_into_blocks(data_codewords, ec_level, version)
        ec_blocks = [ReedSolomon.encode(block, ec_per_block) for block in blocks]
        
        # 6. 交织
        interleaved_data = DataEncoder.interleave(blocks)
        interleaved_ec = DataEncoder.interleave(ec_blocks)
        
        # 7. 最终比特流
        remainder = VersionSelector.get_remainder_bits(version)
        final_bits = DataEncoder.build_final_bitstream(interleaved_data, interleaved_ec, remainder)
        
        # 8. 选择最佳掩码
        temp_matrix = QRMatrix(version)
        temp_matrix.place_function_patterns(ec_level, 0)
        temp_matrix.place_data(final_bits)
        best_mask = Masker.select_best_mask(temp_matrix, final_bits, ec_level)
        
        # 9. 构建最终矩阵
        final_matrix = QRMatrix(version)
        final_matrix.place_function_patterns(ec_level, best_mask)
        final_matrix.place_data(final_bits)
        Masker.apply_mask(final_matrix, best_mask)
        
        # 10. 输出
        if output_format == 'ascii':
            return Renderer.to_ascii(final_matrix)
        elif output_format == 'svg':
            return Renderer.to_svg(final_matrix)
        elif output_format == 'matrix':
            return Renderer.to_boolean_matrix(final_matrix)
        else:
            raise ValueError(f"Unknown format: {output_format}")


# ============================================================
# 测试代码
# ============================================================

if __name__ == '__main__':
    print("=" * 70)
    print("二维码生成器测试（符合 ISO/IEC 18004 标准）")
    print("=" * 70)
    
    test_cases = [
        ("Hello, QR Code!", EC_LEVEL_M, "短文本-M级"),
        ("1234567890", EC_LEVEL_L, "数字-L级"),
        ("https://www.example.com/qrcode/test/12345", EC_LEVEL_H, "URL-H级"),
        ("测试中文编码：这是一段用来验证二维码生成器的中文文本内容，用于测试版本自动选择功能。", EC_LEVEL_M, "中文-M级"),
    ]
    
    for text, ec_level, desc in test_cases:
        print(f"\n{'=' * 70}")
        print(f"测试: {desc}")
        print(f"文本: {text}")
        print(f"纠错等级: {EC_LEVEL_NAMES[ec_level]}")
        print("-" * 70)
        
        try:
            # 自动选择版本
            qr_ascii = QRCodeGenerator.generate(text, ec_level=ec_level, output_format='ascii')
            print(qr_ascii)
            
            # 保存SVG
            svg = QRCodeGenerator.generate(text, ec_level=ec_level, output_format='svg')
            safe_name = ''.join(c if c.isalnum() else '_' for c in text[:15])
            fname = f"qr_{safe_name}_{EC_LEVEL_NAMES[ec_level]}.svg"
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(svg)
            print(f"\n✓ SVG已保存: {fname}")
            
            # 输出版本信息
            v = VersionSelector.select_version(text, ec_level)
            print(f"✓ 自动选择版本: {v} (矩阵大小: {17+v*4}x{17+v*4})")
            
        except Exception as e:
            print(f"✗ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    # 测试大版本
    print(f"\n{'=' * 70}")
    print("测试版本7+的版本信息编码")
    print("=" * 70)
    
    long_text = "A" * 200  # 足够长的文本，会选择版本7+
    for ec in [EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H]:
        try:
            v = VersionSelector.select_version(long_text, ec)
            print(f"纠错等级 {EC_LEVEL_NAMES[ec]}: 选择版本 {v}")
            svg = QRCodeGenerator.generate(long_text, ec_level=ec, output_format='svg')
            fname = f"qr_v{v}_{EC_LEVEL_NAMES[ec]}_long.svg"
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(svg)
            print(f"  ✓ 已保存: {fname}")
        except Exception as e:
            print(f"纠错等级 {EC_LEVEL_NAMES[ec]}: 错误 - {e}")
    
    print("\n" + "=" * 70)
    print("测试掩码选择：验证同一段文本选出规范评分最低的掩码")
    print("=" * 70)
    
    # 测试掩码评分
    test_text = "https://example.com"
    version = VersionSelector.select_version(test_text, EC_LEVEL_M)
    print(f"文本: {test_text}")
    print(f"版本: {version}, 纠错等级: M")
    print()
    
    # 打印8种掩码的惩罚分
    bits, cc = DataEncoder.encode_byte_mode(test_text)
    bits = DataEncoder.adjust_char_count_indicator(bits, cc, version)
    cap = QR_CAPACITY_TABLE[EC_LEVEL_M][version]
    bits = DataEncoder.pad_bits(bits, cap['total_data_codewords'] * 8)
    data_cw = DataEncoder.bits_to_bytes(bits)
    blocks, ec_per = DataEncoder.split_into_blocks(data_cw, EC_LEVEL_M, version)
    ec_blocks = [ReedSolomon.encode(b, ec_per) for b in blocks]
    interleaved_data = DataEncoder.interleave(blocks)
    interleaved_ec = DataEncoder.interleave(ec_blocks)
    rem = VersionSelector.get_remainder_bits(version)
    final_bits = DataEncoder.build_final_bitstream(interleaved_data, interleaved_ec, rem)
    
    temp_matrix = QRMatrix(version)
    temp_matrix.place_function_patterns(EC_LEVEL_M, 0)
    temp_matrix.place_data(final_bits)
    
    print("  掩码  惩罚分")
    print("  ----  ------")
    penalties = []
    for mask in range(8):
        temp = QRMatrix(version)
        temp.place_function_patterns(EC_LEVEL_M, mask)
        temp.place_data(final_bits)
        masked = Masker.apply_mask_temp(temp, mask)
        eval_mat = [[False if v is None else v for v in row] for row in masked]
        p = Masker.calculate_penalty(eval_mat)
        penalties.append((p, mask))
        print(f"    {mask}    {p:4d}")
    
    penalties.sort()
    print(f"\n✓ 最佳掩码: {penalties[0][1]} (惩罚分: {penalties[0][0]})")
    print(f"✓ 最差掩码: {penalties[-1][1]} (惩罚分: {penalties[-1][0]})")
    
    print("\n" + "=" * 70)
    print("所有测试完成！")
    print("=" * 70)
