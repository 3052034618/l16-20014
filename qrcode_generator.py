#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二维码生成器完整实现
包含：数据编码(字节模式)、里德-所罗门纠错、矩阵布局、掩码选择、SVG/点阵渲染
"""

import math
import io
from typing import List, Tuple, Optional

# ============================================================
# 第一部分：GF(256) 有限域运算 + 里德-所罗门纠错码
# ============================================================

class GaloisField:
    """GF(256) 有限域，使用本原多项式 x^8 + x^4 + x^3 + x^2 + 1 (0x11d)"""
    
    # 预计算的指数表和对数表
    EXP_TABLE = [0] * 512
    LOG_TABLE = [0] * 256
    
    @staticmethod
    def _init_tables():
        """初始化 GF(256) 的指数和对数表"""
        x = 1
        for i in range(255):
            GaloisField.EXP_TABLE[i] = x
            GaloisField.LOG_TABLE[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11d  # 模本原多项式
        # 扩展指数表便于计算
        for i in range(255, 512):
            GaloisField.EXP_TABLE[i] = GaloisField.EXP_TABLE[i - 255]
    
    @staticmethod
    def add(a: int, b: int) -> int:
        """GF(256) 加法 = XOR"""
        return a ^ b
    
    @staticmethod
    def sub(a: int, b: int) -> int:
        """GF(256) 减法 = XOR（与加法相同）"""
        return a ^ b
    
    @staticmethod
    def mul(a: int, b: int) -> int:
        """GF(256) 乘法"""
        if a == 0 or b == 0:
            return 0
        return GaloisField.EXP_TABLE[GaloisField.LOG_TABLE[a] + GaloisField.LOG_TABLE[b]]
    
    @staticmethod
    def div(a: int, b: int) -> int:
        """GF(256) 除法"""
        if b == 0:
            raise ZeroDivisionError()
        if a == 0:
            return 0
        return GaloisField.EXP_TABLE[(GaloisField.LOG_TABLE[a] - GaloisField.LOG_TABLE[b]) % 255]
    
    @staticmethod
    def pow(a: int, n: int) -> int:
        """GF(256) 幂运算"""
        if a == 0:
            return 0
        return GaloisField.EXP_TABLE[(GaloisField.LOG_TABLE[a] * n) % 255]
    
    @staticmethod
    def inverse(a: int) -> int:
        """GF(256) 乘法逆元"""
        if a == 0:
            raise ZeroDivisionError()
        return GaloisField.EXP_TABLE[255 - GaloisField.LOG_TABLE[a]]

# 初始化 GF(256) 表
GaloisField._init_tables()


class ReedSolomon:
    """里德-所罗门编码器"""
    
    @staticmethod
    def multiply_polys(a: List[int], b: List[int]) -> List[int]:
        """GF(256) 上的多项式乘法"""
        result = [0] * (len(a) + len(b) - 1)
        for i in range(len(a)):
            for j in range(len(b)):
                result[i + j] = GaloisField.add(result[i + j], GaloisField.mul(a[i], b[j]))
        return result
    
    @staticmethod
    def mod_polys(dividend: List[int], divisor: List[int]) -> List[int]:
        """GF(256) 上的多项式取模（多项式长除法的余数）"""
        result = list(dividend)
        while len(result) >= len(divisor):
            if result[0] != 0:
                coef = result[0]
                for i in range(len(divisor)):
                    result[i] = GaloisField.sub(result[i], GaloisField.mul(coef, divisor[i]))
            result = result[1:]  # 去掉最高次项
        return result
    
    @staticmethod
    def generate_generator_poly(nsym: int) -> List[int]:
        """
        生成 RS 生成多项式 g(x) = (x - α^0)(x - α^1)...(x - α^(nsym-1))
        在 GF(256) 中，-1 = 1（特征为2），所以 (x - α^i) = (x + α^i)
        """
        g = [1]
        for i in range(nsym):
            # 乘以 (x - α^i) = (1*x + α^i)
            g = ReedSolomon.multiply_polys(g, [1, GaloisField.EXP_TABLE[i]])
        return g
    
    @staticmethod
    def encode(data: List[int], nsym: int) -> List[int]:
        """
        对数据进行 RS 编码，返回纠错码字
        
        Args:
            data: 数据码字列表
            nsym: 纠错码字数量
            
        Returns:
            纠错码字列表（长度为 nsym）
        """
        g = ReedSolomon.generate_generator_poly(nsym)
        # 将数据多项式左移 nsym 位（相当于乘以 x^nsym）
        padded = data + [0] * nsym
        # 计算 padded mod g，得到余数（纠错码字）
        remainder = ReedSolomon.mod_polys(padded, g)
        return remainder


# ============================================================
# 第二部分：QR码常量（版本信息、容量、纠错等级等）
# ============================================================

# 纠错等级：L(低, 7%), M(中, 15%), Q(四分位, 25%), H(高, 30%)
EC_LEVEL_L = 0
EC_LEVEL_M = 1
EC_LEVEL_Q = 2
EC_LEVEL_H = 3

EC_LEVEL_NAMES = {EC_LEVEL_L: 'L', EC_LEVEL_M: 'M', EC_LEVEL_Q: 'Q', EC_LEVEL_H: 'H'}

# 模式指示符（4位）
MODE_BYTE = 0b0100  # 字节模式

# ========================
# 版本1-10的容量信息：(数据码字数, 纠错码字数/块, 块数1, 块数2)
# 格式：EC_LEVEL -> version -> (total_data_codewords, ec_per_block, num_blocks_g1, data_per_block_g1, num_blocks_g2, data_per_block_g2)
# ========================

# 完整的 QR 码容量表（版本 1-40）
# 参考 ISO/IEC 18004 标准
QR_CAPACITY_TABLE = {
    EC_LEVEL_L: {},
    EC_LEVEL_M: {},
    EC_LEVEL_Q: {},
    EC_LEVEL_H: {},
}

def _init_capacity_table():
    """初始化 QR 码容量表"""
    # 数据：版本 -> [L, M, Q, H] -> (总数据码字数, 纠错/块, 块1数, 每块数据1, 块2数, 每块数据2)
    data = {
        1: [(19, 7, 1, 19, 0, 0), (16, 10, 1, 16, 0, 0), (13, 13, 1, 13, 0, 0), (9, 17, 1, 9, 0, 0)],
        2: [(34, 10, 1, 34, 0, 0), (28, 16, 1, 28, 0, 0), (22, 22, 1, 22, 0, 0), (16, 28, 1, 16, 0, 0)],
        3: [(55, 15, 1, 55, 0, 0), (44, 26, 1, 44, 0, 0), (34, 18, 2, 17, 0, 0), (26, 22, 2, 13, 0, 0)],
        4: [(80, 20, 1, 80, 0, 0), (64, 18, 2, 32, 0, 0), (48, 26, 2, 24, 0, 0), (36, 16, 4, 9, 0, 0)],
        5: [(108, 26, 1, 108, 0, 0), (86, 24, 2, 43, 0, 0), (62, 18, 2, 15, 2, 16), (46, 22, 2, 11, 2, 12)],
        6: [(136, 18, 2, 68, 0, 0), (108, 16, 4, 27, 0, 0), (76, 24, 4, 19, 0, 0), (60, 28, 4, 15, 0, 0)],
        7: [(156, 20, 2, 78, 0, 0), (124, 18, 4, 31, 0, 0), (88, 18, 2, 14, 4, 15), (66, 26, 4, 13, 1, 14)],
        8: [(194, 24, 2, 97, 0, 0), (154, 22, 2, 38, 2, 39), (110, 22, 4, 18, 2, 19), (86, 26, 4, 14, 2, 15)],
        9: [(232, 30, 2, 116, 0, 0), (182, 22, 3, 36, 2, 37), (132, 20, 4, 16, 4, 17), (100, 24, 4, 12, 4, 13)],
        10: [(274, 18, 2, 68, 2, 69), (216, 26, 4, 43, 1, 44), (154, 24, 6, 19, 2, 20), (122, 28, 6, 15, 2, 16)],
    }
    
    # 补充版本 11-40（简化版，用于支持更大版本）
    # 这里提供版本 11-20 的数据
    more_data = {
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
    }
    data.update(more_data)
    
    for version, levels in data.items():
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

# 对齐图案位置表（版本 >= 2）
ALIGNMENT_PATTERN_POSITIONS = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
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
}

# 格式信息 BCH 码生成多项式 (x^10 + x^8 + x^5 + x^4 + x^2 + x + 1)
FORMAT_INFO_GEN_POLY = 0b10100110111
# 格式信息掩码
FORMAT_INFO_MASK = 0b101010000010010

# 版本信息 BCH 码生成多项式 (x^12 + x^11 + x^10 + x^9 + x^8 + x^5 + x^2 + 1)
VERSION_INFO_GEN_POLY = 0b1111100100101


# ============================================================
# 第三部分：数据编码与分块
# ============================================================

class DataEncoder:
    """数据编码器：字节模式"""
    
    @staticmethod
    def encode_byte_mode(text: str) -> List[int]:
        """
        将文本编码为字节模式的比特流
        
        字节模式结构：
        - 模式指示符: 4 bits (0100)
        - 字符数指示符: 8 bits (版本1-9) 或 16 bits (版本10-40)
        - 数据字节: 每个字符 8 bits
        - 终止符: 最多 4 bits 的 0
        - 补齐: 先补 0 对齐到字节，再交替用 0xEC 和 0x11 补齐
        """
        # 转换为 UTF-8 字节
        data_bytes = text.encode('utf-8')
        bits = []
        
        # 模式指示符 (4 bits): 0100
        bits.extend([0, 1, 0, 0])
        
        # 字符数指示符：先占位，版本确定后填充
        # 这里先用 16 位，后续再根据版本调整
        char_count = len(data_bytes)
        char_count_bits = format(char_count, '016b')
        bits.extend([int(b) for b in char_count_bits])
        
        # 数据字节
        for byte in data_bytes:
            bits.extend([int(b) for b in format(byte, '08b')])
        
        return bits, char_count
    
    @staticmethod
    def pad_bits(bits: List[int], total_data_bits: int, version: int) -> List[int]:
        """
        补齐比特流到指定长度
        
        规则：
        1. 添加终止符（最多 4 个 0 位）
        2. 补 0 使长度为 8 的倍数
        3. 交替填充 0xEC (11101100) 和 0x11 (00010001) 直到达到总长度
        """
        result = list(bits)
        
        # 1. 添加终止符
        terminator_len = min(4, total_data_bits - len(result))
        result.extend([0] * terminator_len)
        
        # 2. 补 0 对齐到字节
        while len(result) % 8 != 0 and len(result) < total_data_bits:
            result.append(0)
        
        # 3. 交替填充补齐字节
        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        while len(result) < total_data_bits:
            pad_byte = pad_bytes[pad_idx % 2]
            pad_idx += 1
            result.extend([int(b) for b in format(pad_byte, '08b')])
        
        return result[:total_data_bits]
    
    @staticmethod
    def bits_to_bytes(bits: List[int]) -> List[int]:
        """将比特流转换为字节列表"""
        bytes_list = []
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                if i + j < len(bits):
                    byte = (byte << 1) | bits[i + j]
            bytes_list.append(byte)
        return bytes_list
    
    @staticmethod
    def adjust_char_count_indicator(bits: List[int], char_count: int, version: int) -> List[int]:
        """
        根据版本调整字符数指示符的位数
        - 版本 1-9: 8 bits
        - 版本 10-26: 16 bits
        - 版本 27-40: 16 bits
        """
        # bits[0:4] 是模式指示符
        # bits[4:20] 是 16 位的字符数（我们之前默认写的 16 位）
        if version <= 9:
            # 只需要 8 位，移除前 8 个字符数位
            cc_bits = [int(b) for b in format(char_count, '08b')]
            return bits[:4] + cc_bits + bits[20:]
        else:
            # 16 位已经正确
            cc_bits = [int(b) for b in format(char_count, '016b')]
            return bits[:4] + cc_bits + bits[20:]
    
    @staticmethod
    def split_into_blocks(data_codewords: List[int], ec_level: int, version: int) -> Tuple[List[List[int]], int]:
        """
        将数据码字分块
        
        返回: (数据块列表, 每块的纠错码字数)
        """
        cap = QR_CAPACITY_TABLE[ec_level][version]
        ec_per_block = cap['ec_per_block']
        nb1 = cap['num_blocks_g1']
        dp1 = cap['data_per_block_g1']
        nb2 = cap['num_blocks_g2']
        dp2 = cap['data_per_block_g2']
        
        blocks = []
        idx = 0
        
        # 第一组块
        for i in range(nb1):
            blocks.append(data_codewords[idx:idx + dp1])
            idx += dp1
        
        # 第二组块
        for i in range(nb2):
            blocks.append(data_codewords[idx:idx + dp2])
            idx += dp2
        
        return blocks, ec_per_block
    
    @staticmethod
    def interleave_data(blocks: List[List[int]]) -> List[int]:
        """交织数据码字：轮流从每块取一个码字"""
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
    def interleave_ec(ec_blocks: List[List[int]]) -> List[int]:
        """交织纠错码字"""
        return DataEncoder.interleave_data(ec_blocks)
    
    @staticmethod
    def build_final_bitstream(data_codewords: List[int], ec_codewords: List[int], remainder_bits: int) -> List[int]:
        """
        构建最终比特流：数据码字 + 纠错码字 + 余位
        
        某些版本在最后需要额外填充 0 位（remainder bits）
        """
        bits = []
        for byte in data_codewords:
            bits.extend([int(b) for b in format(byte, '08b')])
        for byte in ec_codewords:
            bits.extend([int(b) for b in format(byte, '08b')])
        # 添加余位
        bits.extend([0] * remainder_bits)
        return bits


# ============================================================
# 第四部分：QR 码矩阵构建
# ============================================================

class QRMatrix:
    """QR 码矩阵"""
    
    def __init__(self, version: int):
        self.version = version
        self.size = 17 + version * 4  # 矩阵边长
        # 矩阵: None = 未放置, True = 深色模块, False = 浅色模块
        self.modules = [[None] * self.size for _ in range(self.size)]
        # 功能区域标记（用于数据放置时跳过）
        self.is_function = [[False] * self.size for _ in range(self.size)]
    
    def get_module(self, row: int, col: int) -> Optional[bool]:
        if 0 <= row < self.size and 0 <= col < self.size:
            return self.modules[row][col]
        return None
    
    def set_module(self, row: int, col: int, value: bool, is_function: bool = False):
        self.modules[row][col] = value
        if is_function:
            self.is_function[row][col] = True
    
    def place_finder_pattern(self, center_row: int, center_col: int):
        """放置定位图案（7x7 的方块，中心3x3深色，外面一圈白色，再外面一圈深色）"""
        for r in range(-3, 4):
            for c in range(-3, 4):
                row = center_row + r
                col = center_col + c
                if 0 <= row < self.size and 0 <= col < self.size:
                    # 定位图案：外框深色，内部环白色，中心3x3深色
                    if abs(r) == 3 or abs(c) == 3 or (abs(r) <= 1 and abs(c) <= 1):
                        self.set_module(row, col, True, is_function=True)
                    else:
                        self.set_module(row, col, False, is_function=True)
    
    def place_separator(self):
        """放置分隔符（定位图案周围的 8x8 白色边框）"""
        # 左上角定位图案的分隔符
        for i in range(8):
            if i < self.size:
                if 7 < self.size:
                    self.set_module(i, 7, False, is_function=True)
                    self.set_module(7, i, False, is_function=True)
        
        # 右上角定位图案的分隔符
        for i in range(8):
            row = i
            col = self.size - 8
            if 0 <= row < self.size and 0 <= col < self.size:
                self.set_module(row, col, False, is_function=True)
            row = 7
            col = self.size - 8 + i
            if 0 <= row < self.size and 0 <= col < self.size:
                self.set_module(row, col, False, is_function=True)
        
        # 左下角定位图案的分隔符
        for i in range(8):
            row = self.size - 8
            col = i
            if 0 <= row < self.size and 0 <= col < self.size:
                self.set_module(row, col, False, is_function=True)
            row = self.size - 8 + i
            col = 7
            if 0 <= row < self.size and 0 <= col < self.size:
                self.set_module(row, col, False, is_function=True)
    
    def place_alignment_pattern(self, center_row: int, center_col: int):
        """放置对齐图案（5x5 的方块，中心深色，中间环白色，外框深色）"""
        # 检查是否与定位图案重叠
        if (center_row <= 7 and center_col <= 7) or \
           (center_row <= 7 and center_col >= self.size - 8) or \
           (center_row >= self.size - 8 and center_col <= 7):
            return
        
        for r in range(-2, 3):
            for c in range(-2, 3):
                row = center_row + r
                col = center_col + c
                if abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0):
                    self.set_module(row, col, True, is_function=True)
                else:
                    self.set_module(row, col, False, is_function=True)
    
    def place_timing_patterns(self):
        """放置定时图案（行6和列6，交替的深色/浅色模块）"""
        for i in range(8, self.size - 8):
            # 水平定时图案（第6行）
            val = (i % 2 == 0)
            self.set_module(6, i, val, is_function=True)
            # 垂直定时图案（第6列）
            self.set_module(i, 6, val, is_function=True)
    
    def place_dark_module(self):
        """放置深色模块（固定位置的深色模块）"""
        row = 4 * self.version + 9
        col = 8
        if 0 <= row < self.size and 0 <= col < self.size:
            self.set_module(row, col, True, is_function=True)
    
    def place_format_info(self, format_info: int):
        """
        放置格式信息（15位，含纠错）
        
        格式信息：
        - 位15,14,13: 纠错等级 (01=L, 00=M, 11=Q, 10=H)
        - 位12,11,10: 掩码编号 (000-111)
        - 位9-0: BCH纠错码 (10位)
        """
        # 格式信息共 15 位，从高位到低位排列
        bits = [(format_info >> i) & 1 for i in range(14, -1, -1)]
        
        # 位置1：围绕左上角定位图案
        # 行8，列0-8（列6是定时图案，跳过）
        positions = [
            # (row, col) for bits 0-8
            (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
            # 继续列8，行7-0
            (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
        ]
        for i, (r, c) in enumerate(positions):
            self.set_module(r, c, bool(bits[i]), is_function=True)
        
        # 位置2：另外两个角
        positions2 = [
            # 行size-1 到 size-7，列8
            (self.size - 1, 8), (self.size - 2, 8), (self.size - 3, 8),
            (self.size - 4, 8), (self.size - 5, 8), (self.size - 6, 8),
            (self.size - 7, 8),
            # 行8，列size-8 到 size-1
            (8, self.size - 8),
            (8, self.size - 7), (8, self.size - 6), (8, self.size - 5),
            (8, self.size - 4), (8, self.size - 3), (8, self.size - 2),
            (8, self.size - 1),
        ]
        for i, (r, c) in enumerate(positions2):
            self.set_module(r, c, bool(bits[i]), is_function=True)
    
    def place_version_info(self, version_info: int):
        """
        放置版本信息（版本 >= 7 时需要，18位）
        """
        # 18 位，从高位到低位
        bits = [(version_info >> i) & 1 for i in range(17, -1, -1)]
        
        # 位置1：右上角定位图案下方，列0-5，行size-11 到 size-9
        idx = 0
        for col in range(6):
            for row in range(self.size - 11, self.size - 8):
                self.set_module(row, col, bool(bits[idx]), is_function=True)
                idx += 1
        
        # 位置2：左下角定位图案右方，行0-5，列size-11 到 size-9
        idx = 0
        for row in range(6):
            for col in range(self.size - 11, self.size - 8):
                self.set_module(row, col, bool(bits[idx]), is_function=True)
                idx += 1
    
    def place_function_patterns(self, ec_level: int, mask_num: int):
        """放置所有功能图案"""
        # 1. 放置三个定位图案
        self.place_finder_pattern(3, 3)           # 左上角
        self.place_finder_pattern(3, self.size - 4)  # 右上角
        self.place_finder_pattern(self.size - 4, 3)  # 左下角
        
        # 2. 放置分隔符
        self.place_separator()
        
        # 3. 放置对齐图案
        if self.version >= 2:
            positions = ALIGNMENT_PATTERN_POSITIONS.get(self.version, [])
            for r in positions:
                for c in positions:
                    self.place_alignment_pattern(r, c)
        
        # 4. 放置定时图案
        self.place_timing_patterns()
        
        # 5. 放置深色模块
        self.place_dark_module()
        
        # 6. 格式信息
        format_data = self._encode_format_info(ec_level, mask_num)
        self.place_format_info(format_data)
        
        # 7. 版本信息（版本 >= 7）
        if self.version >= 7:
            version_data = self._encode_version_info(self.version)
            self.place_version_info(version_data)
    
    def _encode_format_info(self, ec_level: int, mask_num: int) -> int:
        """
        编码格式信息：5位数据 + 10位BCH纠错 + 异或掩码
        
        数据位：
        - 2位：纠错等级 (01=L, 00=M, 11=Q, 10=H)
        - 3位：掩码编号
        """
        # 纠错等级编码
        ec_codes = {
            EC_LEVEL_L: 0b01,
            EC_LEVEL_M: 0b00,
            EC_LEVEL_Q: 0b11,
            EC_LEVEL_H: 0b10,
        }
        data = (ec_codes[ec_level] << 3) | mask_num  # 5位
        
        # BCH(15,5) 编码：计算10位纠错码
        d = data << 10
        gen = FORMAT_INFO_GEN_POLY  # 11位
        
        # 多项式取模
        for i in range(4, -1, -1):
            if (d >> (i + 10)) & 1:
                d ^= gen << i
        
        # 组合并异或掩码
        result = ((data << 10) | d) ^ FORMAT_INFO_MASK
        return result
    
    def _encode_version_info(self, version: int) -> int:
        """
        编码版本信息：6位版本号 + 12位BCH纠错
        """
        v = version << 12
        gen = VERSION_INFO_GEN_POLY  # 13位
        
        for i in range(5, -1, -1):
            if (v >> (i + 12)) & 1:
                v ^= gen << i
        
        return (version << 12) | v
    
    def place_data(self, data_bits: List[int]):
        """
        将数据比特放置到矩阵中
        
        放置规则：
        - 从右下角开始，蛇形向上/向下移动
        - 每次处理两列（除了被定时图案占据的第6列）
        - 在 2 列宽的条带中，以 2x1 或 1x2 的方式放置
        - 跳过功能模块
        """
        bit_idx = 0
        total_bits = len(data_bits)
        size = self.size
        
        # 从右往左，每次跳2列（跳过列6）
        col = size - 1
        while col > 0:
            if col == 6:  # 跳过定时图案所在列
                col -= 1
                continue
            
            # 向上或向下遍历
            # 确定当前条带的方向
            is_upward = ((col - 1) // 2) % 2 == 0  # 第1对(列0,1不处理)从下往上
            
            # 实际上：从最后一列开始，方向交替
            # 列(size-1, size-2): 从下往上
            # 列(size-3, size-4): 从上往下
            # 等等...
            pair_idx = (size - 1 - col) // 2
            is_upward = (pair_idx % 2 == 0)
            
            if is_upward:
                rows = range(size - 1, -1, -1)
            else:
                rows = range(size)
            
            for row in rows:
                for c_offset in [0, 1]:  # 先右列，再左列
                    c = col - c_offset
                    if bit_idx >= total_bits:
                        return
                    if not self.is_function[row][c] and self.modules[row][c] is None:
                        self.set_module(row, c, bool(data_bits[bit_idx]))
                        bit_idx += 1
            
            col -= 2


# ============================================================
# 第五部分：掩码算法与惩罚评分
# ============================================================

class Masker:
    """8种数据掩码算法"""
    
    @staticmethod
    def mask_function(mask_num: int, row: int, col: int) -> bool:
        """
        8种掩码函数：返回 True 表示该位置需要翻转
        
        掩码条件（满足则翻转）：
        0: (row + col) % 2 == 0
        1: row % 2 == 0
        2: col % 3 == 0
        3: (row + col) % 3 == 0
        4: (floor(row/2) + floor(col/3)) % 2 == 0
        5: (row*col) % 2 + (row*col) % 3 == 0
        6: ((row*col) % 2 + (row*col) % 3) % 2 == 0
        7: ((row+col) % 2 + (row*col) % 3) % 2 == 0
        """
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
            return ((row * col) % 2) + ((row * col) % 3) == 0
        elif mask_num == 6:
            return (((row * col) % 2) + ((row * col) % 3)) % 2 == 0
        elif mask_num == 7:
            return (((row + col) % 2) + ((row * col) % 3)) % 2 == 0
        else:
            raise ValueError(f"Invalid mask number: {mask_num}")
    
    @staticmethod
    def apply_mask(matrix: QRMatrix, mask_num: int):
        """对数据模块应用掩码（不改变功能模块）"""
        for r in range(matrix.size):
            for c in range(matrix.size):
                if not matrix.is_function[r][c]:
                    if Masker.mask_function(mask_num, r, c):
                        matrix.modules[r][c] = not matrix.modules[r][c]
    
    @staticmethod
    def apply_mask_temp(matrix: QRMatrix, mask_num: int) -> List[List[bool]]:
        """临时应用掩码，返回新的矩阵（不修改原矩阵）"""
        result = []
        for r in range(matrix.size):
            row = []
            for c in range(matrix.size):
                val = matrix.modules[r][c]
                if not matrix.is_function[r][c] and val is not None:
                    if Masker.mask_function(mask_num, r, c):
                        val = not val
                row.append(val)
            result.append(row)
        return result
    
    @staticmethod
    def calculate_penalty(modules: List[List[bool]]) -> int:
        """
        计算惩罚分数（越低越好）
        
        四个惩罚规则：
        N1: 行/列中有连续5个相同颜色的模块（每5个+3，每多1个+1）
        N2: 2x2 的同色方块（每个+3）
        N3: 出现类似定位图案的序列（1:1:3:1:1 比例的深色-浅色-深色-浅色-深色）
        N4: 深色模块比例偏离50%的程度（每偏离5%+10）
        """
        size = len(modules)
        penalty = 0
        
        # N1: 连续相同颜色
        for r in range(size):
            count = 1
            for c in range(1, size):
                if modules[r][c] == modules[r][c - 1]:
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
                if modules[r][c] == modules[r - 1][c]:
                    count += 1
                else:
                    if count >= 5:
                        penalty += 3 + (count - 5)
                    count = 1
            if count >= 5:
                penalty += 3 + (count - 5)
        
        # N2: 2x2 同色方块
        for r in range(size - 1):
            for c in range(size - 1):
                v = modules[r][c]
                if v is not None and v == modules[r][c + 1] == modules[r + 1][c] == modules[r + 1][c + 1]:
                    penalty += 3
        
        # N3: 定位图案类似序列
        # 检测 深色-浅色-深色-深色-深色-浅色-深色 (1:1:3:1:1 比例)
        pattern = [True, False, True, True, True, False, True]
        
        # 行检测
        for r in range(size):
            for c in range(size - 6):
                match = True
                for i in range(7):
                    if modules[r][c + i] != pattern[i]:
                        match = False
                        break
                if match:
                    penalty += 40
        
        # 列检测
        for c in range(size):
            for r in range(size - 6):
                match = True
                for i in range(7):
                    if modules[r + i][c] != pattern[i]:
                        match = False
                        break
                if match:
                    penalty += 40
        
        # N4: 深色比例
        dark_count = 0
        total = 0
        for r in range(size):
            for c in range(size):
                if modules[r][c] is not None:
                    total += 1
                    if modules[r][c]:
                        dark_count += 1
        
        if total > 0:
            percent = dark_count * 100 / total
            # 找最接近的5%倍数，计算与50%的偏差
            k = abs(percent - 50) / 5
            penalty += int(k) * 10
        
        return penalty
    
    @staticmethod
    def select_best_mask(matrix: QRMatrix, data_bits: List[int], ec_level: int) -> int:
        """
        选择惩罚分数最低的掩码（0-7）
        """
        best_mask = 0
        best_penalty = float('inf')
        
        for mask_num in range(8):
            # 创建临时矩阵并放置数据
            temp_matrix = QRMatrix(matrix.version)
            temp_matrix.place_function_patterns(ec_level, mask_num)
            temp_matrix.place_data(data_bits)
            
            # 应用掩码
            masked_modules = Masker.apply_mask_temp(temp_matrix, mask_num)
            
            # 计算惩罚（转换 None 为 False 便于评估）
            eval_modules = [[False if v is None else v for v in row] for row in masked_modules]
            penalty = Masker.calculate_penalty(eval_modules)
            
            if penalty < best_penalty:
                best_penalty = penalty
                best_mask = mask_num
        
        return best_mask


# ============================================================
# 第六部分：版本选择
# ============================================================

class VersionSelector:
    """版本选择器"""
    
    @staticmethod
    def get_remainder_bits(version: int) -> int:
        """获取指定版本的余位数"""
        # 余位表：版本1-40
        # 参考 ISO/IEC 18004
        remainder_table = [
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 1-10
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 11-20
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 21-30
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 31-40
        ]
        # 实际上：
        # 版本 1: 0 bits
        # 版本 2: 7 bits
        # 版本 3: 7 bits
        # 版本 4: 7 bits
        # 版本 5: 7 bits  
        # 版本 6: 7 bits
        # 版本 7: 0 bits
        # 版本 8: 0 bits
        # 版本 9: 0 bits
        # 版本 10: 0 bits
        # ... 简化起见，用更精确的表
        precise_remainder = {
            1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7,
            7: 0, 8: 0, 9: 0, 10: 0,
            11: 0, 12: 0, 13: 0, 14: 3, 15: 3, 16: 3,
            17: 3, 18: 3, 19: 3, 20: 3,
        }
        return precise_remainder.get(version, 0)
    
    @staticmethod
    def select_version(text: str, ec_level: int) -> int:
        """
        根据数据量和纠错等级选择最小的版本
        
        Args:
            text: 要编码的文本
            ec_level: 纠错等级
            
        Returns:
            版本号 (1-40)
        """
        data_bytes = text.encode('utf-8')
        char_count = len(data_bytes)
        
        # 遍历版本 1-20（我们实现支持的范围）
        for version in range(1, 21):
            cap = QR_CAPACITY_TABLE.get(ec_level, {}).get(version)
            if cap is None:
                continue
            
            total_data_codewords = cap['total_data_codewords']
            total_data_bits = total_data_codewords * 8
            
            # 计算所需位数
            # 模式指示符: 4 bits
            # 字符数指示符: 8 bits (v1-9) 或 16 bits (v10+)
            cc_bits = 8 if version <= 9 else 16
            # 数据字节: 每个 8 bits
            data_bits_count = char_count * 8
            
            total_needed = 4 + cc_bits + data_bits_count
            
            # 需要留出至少终止符 (4 bits)
            if total_needed + 4 <= total_data_bits:
                return version
        
        raise ValueError("数据过大，超出支持的版本范围（最大版本20）")


# ============================================================
# 第七部分：渲染（点阵打印 + SVG输出）
# ============================================================

class Renderer:
    """渲染器"""
    
    @staticmethod
    def to_ascii(matrix: QRMatrix, quiet_zone: int = 4) -> str:
        """
        渲染为 ASCII 字符画
        """
        size = matrix.size + quiet_zone * 2
        lines = []
        
        for r in range(size):
            line = []
            for c in range(size):
                mr = r - quiet_zone
                mc = c - quiet_zone
                if 0 <= mr < matrix.size and 0 <= mc < matrix.size:
                    val = matrix.modules[mr][mc]
                    if val is None:
                        line.append('?')
                    elif val:
                        line.append('█')
                    else:
                        line.append(' ')
                else:
                    line.append(' ')
            lines.append(''.join(line))
        
        return '\n'.join(lines)
    
    @staticmethod
    def to_svg(matrix: QRMatrix, module_size: int = 10, quiet_zone: int = 4, 
               fg_color: str = '#000000', bg_color: str = '#ffffff') -> str:
        """
        渲染为 SVG 图像
        """
        size = matrix.size + quiet_zone * 2
        pixel_size = size * module_size
        
        svg_parts = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pixel_size} {pixel_size}" width="{pixel_size}" height="{pixel_size}">',
            f'  <rect width="{pixel_size}" height="{pixel_size}" fill="{bg_color}"/>',
        ]
        
        for r in range(matrix.size):
            for c in range(matrix.size):
                val = matrix.modules[r][c]
                if val:  # 深色模块
                    x = (c + quiet_zone) * module_size
                    y = (r + quiet_zone) * module_size
                    svg_parts.append(
                        f'  <rect x="{x}" y="{y}" width="{module_size}" height="{module_size}" fill="{fg_color}"/>'
                    )
        
        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)
    
    @staticmethod
    def to_boolean_matrix(matrix: QRMatrix, quiet_zone: int = 4) -> List[List[bool]]:
        """
        渲染为布尔矩阵（True=深色, False=浅色）
        """
        size = matrix.size + quiet_zone * 2
        result = []
        
        for r in range(size):
            row = []
            for c in range(size):
                mr = r - quiet_zone
                mc = c - quiet_zone
                if 0 <= mr < matrix.size and 0 <= mc < matrix.size:
                    val = matrix.modules[mr][mc]
                    row.append(bool(val))
                else:
                    row.append(False)
            result.append(row)
        
        return result


# ============================================================
# 第八部分：主入口
# ============================================================

class QRCodeGenerator:
    """二维码生成器主类"""
    
    @staticmethod
    def generate(text: str, ec_level: int = EC_LEVEL_M, 
                 output_format: str = 'ascii'):
        """
        生成二维码
        
        Args:
            text: 要编码的文本
            ec_level: 纠错等级 (L/M/Q/H)
            output_format: 'ascii', 'svg', 'matrix'
            
        Returns:
            根据格式返回字符串或矩阵
        """
        # 1. 选择版本
        version = VersionSelector.select_version(text, ec_level)
        
        # 2. 数据编码（字节模式）
        bits, char_count = DataEncoder.encode_byte_mode(text)
        
        # 3. 调整字符数指示符位数
        bits = DataEncoder.adjust_char_count_indicator(bits, char_count, version)
        
        # 4. 获取总数据比特数并补齐
        cap = QR_CAPACITY_TABLE[ec_level][version]
        total_data_bits = cap['total_data_codewords'] * 8
        bits = DataEncoder.pad_bits(bits, total_data_bits, version)
        
        # 5. 转换为码字
        data_codewords = DataEncoder.bits_to_bytes(bits)
        
        # 6. 分块
        blocks, ec_per_block = DataEncoder.split_into_blocks(data_codewords, ec_level, version)
        
        # 7. 为每块生成纠错码字
        ec_blocks = []
        for block in blocks:
            ec_words = ReedSolomon.encode(block, ec_per_block)
            ec_blocks.append(ec_words)
        
        # 8. 交织数据和纠错码字
        interleaved_data = DataEncoder.interleave_data(blocks)
        interleaved_ec = DataEncoder.interleave_ec(ec_blocks)
        
        # 9. 构建最终比特流（含余位）
        remainder_bits = VersionSelector.get_remainder_bits(version)
        final_bits = DataEncoder.build_final_bitstream(
            interleaved_data, interleaved_ec, remainder_bits
        )
        
        # 10. 创建矩阵，放置功能图案（先用掩码0占位）
        matrix = QRMatrix(version)
        matrix.place_function_patterns(ec_level, 0)
        matrix.place_data(final_bits)
        
        # 11. 选择最佳掩码
        best_mask = Masker.select_best_mask(matrix, final_bits, ec_level)
        
        # 12. 用最佳掩码重新构建最终矩阵
        final_matrix = QRMatrix(version)
        final_matrix.place_function_patterns(ec_level, best_mask)
        final_matrix.place_data(final_bits)
        
        # 13. 应用掩码
        Masker.apply_mask(final_matrix, best_mask)
        
        # 14. 输出
        if output_format == 'ascii':
            return Renderer.to_ascii(final_matrix)
        elif output_format == 'svg':
            return Renderer.to_svg(final_matrix)
        elif output_format == 'matrix':
            return Renderer.to_boolean_matrix(final_matrix)
        else:
            raise ValueError(f"Unknown output format: {output_format}")


# ============================================================
# 测试代码
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("二维码生成器测试")
    print("=" * 60)
    
    # 测试文本
    test_texts = [
        "Hello, QR Code!",
        "1234567890",
        "https://www.example.com",
    ]
    
    for text in test_texts:
        print(f"\n\n编码文本: {text}")
        print("-" * 60)
        try:
            # ASCII 输出
            ascii_qr = QRCodeGenerator.generate(text, ec_level=EC_LEVEL_M, output_format='ascii')
            print(ascii_qr)
            
            # SVG 输出保存到文件
            svg_qr = QRCodeGenerator.generate(text, ec_level=EC_LEVEL_M, output_format='svg')
            filename = f"qrcode_{text[:10].replace('/', '_')}.svg"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(svg_qr)
            print(f"\nSVG 已保存到: {filename}")
            
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
