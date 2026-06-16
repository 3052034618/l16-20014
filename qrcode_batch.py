#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二维码批量生成工具
支持：
  1. 从 TXT（每行一条）或 CSV 读取内容批量生成
  2. 输出 SVG 或 PNG（点阵）文件，文件名带序号
  3. 生成 CSV 报告（版本、纠错等级、掩码、尺寸、字节数等）
  4. 自检模式：与标准库 qrcode 做矩阵级对比
  5. 清晰的成功/失败统计

用法示例：
  python qrcode_batch.py -i input.txt -o output_dir -f svg
  python qrcode_batch.py -i input.csv -o output_dir -f svg --csv-col content
  python qrcode_batch.py -t "Hello" -t "你好" -o out -f svg --selfcheck
"""

import os
import re
import sys
import csv
import json
import argparse
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from qrcode_generator import (
    QRCodeGenerator, QRMatrix, DataEncoder, ReedSolomon, Masker, VersionSelector,
    EC_LEVEL_L, EC_LEVEL_M, EC_LEVEL_Q, EC_LEVEL_H,
    EC_LEVEL_NAMES, QR_CAPACITY_TABLE,
)

# 自检使用的标准库
try:
    import qrcode as std_qrcode
    STD_QR_AVAILABLE = True
except ImportError:
    STD_QR_AVAILABLE = False


EC_LEVEL_MAP = {
    'L': EC_LEVEL_L,
    'M': EC_LEVEL_M,
    'Q': EC_LEVEL_Q,
    'H': EC_LEVEL_H,
}


# ============================================================
# 输入读取
# ============================================================

def read_txt(filepath: str) -> List[str]:
    """从 TXT 读取，每行一条内容（跳过空行和#开头的注释行）"""
    items: List[str] = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if line.strip() == '' or line.strip().startswith('#'):
                continue
            items.append(line)
    return items


def read_csv(filepath: str, column: Optional[str] = None,
             encoding: str = 'utf-8') -> List[str]:
    """
    从 CSV 读取内容
    column: 指定内容列的列名或列索引（从0开始），None 表示取第一列
    """
    items: List[str] = []
    with open(filepath, 'r', encoding=encoding, newline='') as f:
        reader = csv.reader(f)
        rows = list(reader)
        if not rows:
            return items

        # 判断是否有表头（默认第一行如果是中文/英文非内容则视为表头）
        start_idx = 0
        col_idx = 0
        if column is not None:
            # 先尝试按列名匹配
            header = rows[0]
            if column in header:
                col_idx = header.index(column)
                start_idx = 1
            else:
                # 按数字索引
                try:
                    col_idx = int(column)
                except ValueError:
                    raise ValueError(f"CSV 中未找到列 '{column}'，有效列: {header}")
        else:
            # 启发式判断：如果第一行看起来像表头（包含"内容/文本/text/content"等词）
            first_row = rows[0]
            header_keywords = ('内容', '文本', 'text', 'content', 'data')
            if any(any(kw in str(cell).lower() for kw in header_keywords) for cell in first_row):
                start_idx = 1

        for row in rows[start_idx:]:
            if col_idx < len(row):
                text = str(row[col_idx]).strip()
                if text:
                    items.append(text)
    return items


def load_items(input_file: Optional[str],
               texts: Optional[List[str]],
               csv_column: Optional[str] = None) -> List[str]:
    """根据输入方式统一加载内容列表"""
    items: List[str] = []

    if texts:
        items.extend(texts)

    if input_file:
        ext = os.path.splitext(input_file)[1].lower()
        if ext == '.txt':
            items.extend(read_txt(input_file))
        elif ext == '.csv':
            items.extend(read_csv(input_file, csv_column))
        else:
            raise ValueError(f"不支持的输入文件格式: {ext}，请使用 .txt 或 .csv")

    return items


# ============================================================
# 文件命名
# ============================================================

def sanitize_filename(text: str, max_len: int = 30) -> str:
    """清理文本生成安全的文件名片段"""
    # 去掉非法字符
    name = re.sub(r'[\\/:*?"<>|\s]+', '_', text)
    # 去掉控制字符
    name = re.sub(r'[\x00-\x1f]', '', name)
    if len(name) > max_len:
        name = name[:max_len]
    return name or 'qr'


def make_output_filename(index: int, text: str, fmt: str,
                         use_text_in_name: bool = True,
                         pad_digits: int = 4) -> str:
    """生成输出文件名：序号 + 文本片段 + 扩展名"""
    prefix = str(index + 1).zfill(pad_digits)
    if use_text_in_name:
        safe = sanitize_filename(text)
        name = f"{prefix}_{safe}.{fmt}"
    else:
        name = f"{prefix}.{fmt}"
    return name


# ============================================================
# 点阵（PNM/PGM）输出 —— 不依赖PIL
# ============================================================

def matrix_to_pbm(matrix, scale: int = 8) -> bytes:
    """
    将布尔矩阵转为 PBM（Portable Bit Map）二进制格式
    PBM 是无依赖的点阵格式，可以用 GIMP/IrfanView/ImageMagick 打开
    """
    h = len(matrix)
    w = len(matrix[0])
    sw, sh = w * scale, h * scale

    # PBM header: P4\nW H\n
    header = f"P4\n{sw} {sh}\n".encode('ascii')

    # 每行按字节打包（MSB first），然后按 scale 行重复
    body = bytearray()
    for r in range(h):
        # 构建一行的比特数据（按 scale 放大列）
        row_bits = []
        for c in range(w):
            bit = 0 if matrix[r][c] else 1  # PBM 0=黑, 1=白，与我们 True=黑相反
            row_bits.extend([bit] * scale)
        # 打包成字节
        row_bytes = []
        for i in range(0, len(row_bits), 8):
            chunk = row_bits[i:i + 8]
            while len(chunk) < 8:
                chunk.append(1)  # 填充白
            byte_val = 0
            for b in chunk:
                byte_val = (byte_val << 1) | b
            row_bytes.append(byte_val)
        # 按 scale 重复这一行
        for _ in range(scale):
            body.extend(row_bytes)

    return header + bytes(body)


# ============================================================
# 自检（与标准库对比）
# ============================================================

def self_check(text: str, ec_level: int, version: int, mask: int
               ) -> Dict[str, Any]:
    """
    与标准库 qrcode 做矩阵级对比
    返回: {'passed': bool, 'diff_count': int, 'std_version': int, 'std_mask': int, 'note': str}
    """
    result: Dict[str, Any] = {
        'passed': False,
        'diff_count': -1,
        'std_version': -1,
        'std_mask': -1,
        'note': '',
    }

    if not STD_QR_AVAILABLE:
        result['note'] = '标准库 qrcode 未安装，跳过自检'
        return result

    try:
        ec_map = {
            EC_LEVEL_L: std_qrcode.constants.ERROR_CORRECT_L,
            EC_LEVEL_M: std_qrcode.constants.ERROR_CORRECT_M,
            EC_LEVEL_Q: std_qrcode.constants.ERROR_CORRECT_Q,
            EC_LEVEL_H: std_qrcode.constants.ERROR_CORRECT_H,
        }

        # 标准库（字节模式）
        qr = std_qrcode.QRCode(
            version=version,
            error_correction=ec_map[ec_level],
            box_size=1,
            border=0,
        )
        data_bytes = text.encode('utf-8')
        qr.add_data(data_bytes, optimize=0)
        qr.make(fit=False)
        std_matrix = qr.get_matrix()
        std_mask = qr.best_mask_pattern()

        # 我们的实现（无静区）
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

        our_matrix_obj = QRMatrix(version)
        our_matrix_obj.place_function_patterns(ec_level, mask)
        our_matrix_obj.place_data(final_bits)
        Masker.apply_mask(our_matrix_obj, mask)

        our_matrix = [[False if v is None else v for v in row] for row in our_matrix_obj.modules]

        # 对比
        s = len(std_matrix)
        diff_count = 0
        for r in range(s):
            for c in range(s):
                if our_matrix[r][c] != std_matrix[r][c]:
                    diff_count += 1

        result['std_version'] = qr.version
        result['std_mask'] = std_mask
        result['diff_count'] = diff_count
        result['passed'] = (diff_count == 0)
        if diff_count == 0:
            result['note'] = '与标准库完全一致'
        else:
            result['note'] = f'与标准库差异: {diff_count} 模块'
            if mask != std_mask:
                result['note'] += f' (掩码不一致: 我们={mask}, 标准={std_mask})'

    except Exception as e:
        result['note'] = f'自检异常: {e}'

    return result


# ============================================================
# 报告生成
# ============================================================

def write_csv_report(report_path: str, records: List[Dict[str, Any]]) -> None:
    """写出 CSV 格式报告"""
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(report_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)


def write_json_report(report_path: str, summary: Dict[str, Any],
                      records: List[Dict[str, Any]]) -> None:
    """写出 JSON 格式完整报告"""
    data = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'summary': summary,
        'items': records,
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text_summary(summary_path: str, summary: Dict[str, Any],
                       records: List[Dict[str, Any]]) -> None:
    """写出人类可读的文本摘要"""
    lines = []
    lines.append("=" * 70)
    lines.append("二维码批量生成报告")
    lines.append("=" * 70)
    lines.append(f"生成时间: {summary['generated_at']}")
    lines.append(f"输出目录: {summary['output_dir']}")
    lines.append(f"输出格式: {summary['output_format']}")
    lines.append(f"纠错等级: {summary['ec_level']}")
    lines.append("")
    lines.append("-" * 70)
    lines.append("统计")
    lines.append("-" * 70)
    lines.append(f"  总数:   {summary['total']}")
    lines.append(f"  成功:   {summary['success']}")
    lines.append(f"  失败:   {summary['failed']}")
    if summary.get('selfcheck_total'):
        lines.append(f"  自检通过: {summary['selfcheck_passed']} / {summary['selfcheck_total']}")
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"{'#':>4}  {'文件':<40} {'V':>2} {'EC':>2} {'M':>2} {'尺寸':>6} {'字节':>5} 状态")
    lines.append("-" * 70)
    for rec in records:
        status = 'OK' if rec['success'] else 'FAIL'
        if rec.get('selfcheck_passed') is False:
            status += '(自检不一致)'
        text_preview = (rec['text'][:30] + '...') if len(rec['text']) > 30 else rec['text']
        lines.append(
            f"{rec['index']+1:>4}  {rec['filename']:<40} "
            f"{rec['version']:>2} {rec['ec_level_name']:>2} {rec['mask']:>2} "
            f"{rec['matrix_size']:>3}x{rec['matrix_size']:<3} {rec['content_bytes']:>5}  "
            f"{status}"
        )
        if not rec['success']:
            lines.append(f"        错误: {rec['error']}")
    lines.append("")
    lines.append("=" * 70)

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ============================================================
# 批量生成主流程
# ============================================================

def batch_generate(items: List[str], output_dir: str,
                   output_format: str = 'svg',
                   ec_level: int = EC_LEVEL_M,
                   force_version: Optional[int] = None,
                   selfcheck: bool = False,
                   use_text_in_name: bool = True,
                   pbm_scale: int = 8,
                   ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    批量生成二维码

    Args:
        items: 内容列表
        output_dir: 输出目录
        output_format: 'svg' 或 'pbm'（点阵）
        ec_level: 纠错等级
        force_version: 强制版本
        selfcheck: 是否启用自检
        use_text_in_name: 文件名是否包含文本片段
        pbm_scale: PBM 点阵放大倍数

    Returns:
        (summary, records)
    """
    os.makedirs(output_dir, exist_ok=True)

    fmt_ext = 'svg' if output_format == 'svg' else 'pbm'
    records: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    selfcheck_total = 0
    selfcheck_passed = 0

    for idx, text in enumerate(items):
        rec: Dict[str, Any] = {
            'index': idx,
            'text': text,
            'filename': '',
            'success': False,
            'error': '',
            'version': 0,
            'ec_level': ec_level,
            'ec_level_name': EC_LEVEL_NAMES[ec_level],
            'mask': -1,
            'matrix_size': 0,
            'content_bytes': 0,
            'char_count': len(text),
            'selfcheck_passed': None,
            'selfcheck_diff': -1,
            'selfcheck_note': '',
        }

        try:
            # 生成
            output, meta = QRCodeGenerator.generate_with_metadata(
                text, ec_level=ec_level,
                output_format='svg' if output_format == 'svg' else 'matrix',
                force_version=force_version,
            )

            # 写文件
            filename = make_output_filename(idx, text, fmt_ext, use_text_in_name)
            filepath = os.path.join(output_dir, filename)

            if output_format == 'svg':
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(output)
            else:  # pbm
                with open(filepath, 'wb') as f:
                    f.write(matrix_to_pbm(output, scale=pbm_scale))

            rec['filename'] = filename
            rec['success'] = True
            rec['version'] = meta['version']
            rec['mask'] = meta['mask']
            rec['matrix_size'] = meta['matrix_size']
            rec['content_bytes'] = meta['content_bytes']
            success_count += 1

            # 自检
            if selfcheck:
                selfcheck_total += 1
                check = self_check(text, ec_level, meta['version'], meta['mask'])
                rec['selfcheck_passed'] = check['passed']
                rec['selfcheck_diff'] = check['diff_count']
                rec['selfcheck_note'] = check['note']
                if check['passed']:
                    selfcheck_passed += 1

        except Exception as e:
            rec['error'] = str(e)
            failed_count += 1

        records.append(rec)

    summary = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'output_dir': os.path.abspath(output_dir),
        'output_format': output_format,
        'ec_level': EC_LEVEL_NAMES[ec_level],
        'force_version': force_version,
        'total': len(items),
        'success': success_count,
        'failed': failed_count,
        'selfcheck_enabled': selfcheck,
        'selfcheck_total': selfcheck_total,
        'selfcheck_passed': selfcheck_passed,
    }

    return summary, records


# ============================================================
# 命令行入口
# ============================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='二维码批量生成工具（符合 ISO/IEC 18004 标准）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 TXT 读取，每行一条，输出 SVG
  python qrcode_batch.py -i input.txt -o out

  # 从 CSV 读取，指定列为 "content"，输出点阵 PBM
  python qrcode_batch.py -i data.csv -o out --csv-col content -f pbm

  # 直接在命令行传内容
  python qrcode_batch.py -t "Hello" -t "https://example.com" -o out

  # 启用自检（与标准库对比）
  python qrcode_batch.py -i input.txt -o out --selfcheck

  # 强制使用版本 5，纠错等级 Q
  python qrcode_batch.py -i input.txt -o out -v 5 -e Q
""")

    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument('-i', '--input', type=str,
                             help='输入文件路径 (.txt 或 .csv)')
    parser.add_argument('-t', '--text', action='append', default=[],
                        help='直接在命令行指定内容（可重复多次）')
    parser.add_argument('--csv-col', type=str, default=None,
                        help='CSV 内容列名或索引（默认自动识别第一列）')

    parser.add_argument('-o', '--output-dir', type=str, default='./qr_output',
                        help='输出目录 (默认: ./qr_output)')
    parser.add_argument('-f', '--format', choices=['svg', 'pbm'], default='svg',
                        help='输出格式: svg 矢量图 或 pbm 点阵图 (默认: svg)')
    parser.add_argument('-e', '--ec-level', choices=['L', 'M', 'Q', 'H'], default='M',
                        help='纠错等级 (默认: M)')
    parser.add_argument('-v', '--version', type=int, default=None,
                        help='强制使用的版本 (1-40)，默认自动选择')

    parser.add_argument('--pbm-scale', type=int, default=8,
                        help='PBM 点阵的放大倍数 (默认: 8)')
    parser.add_argument('--no-text-in-name', action='store_true',
                        help='文件名不包含文本片段（只用序号）')

    parser.add_argument('--selfcheck', action='store_true',
                        help='启用自检模式：与标准库 qrcode 做矩阵级对比')
    parser.add_argument('--report', choices=['txt', 'csv', 'json', 'all'], default='all',
                        help='报告格式 (默认: all)')
    parser.add_argument('--report-name', type=str, default='qr_report',
                        help='报告文件名前缀 (默认: qr_report)')

    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 校验：必须有输入
    if not args.input and not args.text:
        parser.print_help()
        print("\n错误: 必须通过 -i 或 -t 指定至少一条内容", file=sys.stderr)
        return 1

    # 加载内容
    try:
        items = load_items(args.input, args.text, args.csv_col)
    except Exception as e:
        print(f"读取输入失败: {e}", file=sys.stderr)
        return 1

    if not items:
        print("未读取到任何内容，退出。", file=sys.stderr)
        return 1

    ec_level = EC_LEVEL_MAP[args.ec_level.upper()]

    print("=" * 70)
    print("二维码批量生成工具")
    print("=" * 70)
    print(f"输入条数:     {len(items)}")
    print(f"输出目录:     {os.path.abspath(args.output_dir)}")
    print(f"输出格式:     {args.format}")
    print(f"纠错等级:     {args.ec_level}")
    if args.version:
        print(f"强制版本:     {args.version}")
    else:
        print(f"强制版本:     自动选择")
    print(f"自检模式:     {'开启' if args.selfcheck else '关闭'}")
    if args.selfcheck and not STD_QR_AVAILABLE:
        print("  ⚠ 标准库 qrcode 未安装，自检将被跳过")
    print()

    # 执行批量生成
    summary, records = batch_generate(
        items=items,
        output_dir=args.output_dir,
        output_format=args.format,
        ec_level=ec_level,
        force_version=args.version,
        selfcheck=args.selfcheck,
        use_text_in_name=not args.no_text_in_name,
        pbm_scale=args.pbm_scale,
    )

    # 控制台打印统计
    print("-" * 70)
    print("生成完成:")
    print(f"  总数:   {summary['total']}")
    print(f"  成功:   {summary['success']}")
    print(f"  失败:   {summary['failed']}")
    if summary['selfcheck_enabled']:
        print(f"  自检通过: {summary['selfcheck_passed']} / {summary['selfcheck_total']}")
    print()

    # 写报告
    report_prefix = os.path.join(args.output_dir, args.report_name)
    if args.report in ('txt', 'all'):
        write_text_summary(report_prefix + '.txt', summary, records)
        print(f"文本报告: {report_prefix}.txt")
    if args.report in ('csv', 'all'):
        write_csv_report(report_prefix + '.csv', records)
        print(f"CSV 报告: {report_prefix}.csv")
    if args.report in ('json', 'all'):
        write_json_report(report_prefix + '.json', summary, records)
        print(f"JSON 报告: {report_prefix}.json")

    # 如果有失败，返回非零退出码
    if summary['failed'] > 0:
        print("\n⚠ 部分内容生成失败，请查看报告。", file=sys.stderr)
        return 2
    if summary['selfcheck_enabled'] and summary['selfcheck_passed'] < summary['selfcheck_total']:
        print("\n⚠ 部分自检未通过，请查看报告。", file=sys.stderr)
        return 3

    print("\n✅ 全部成功！")
    return 0


if __name__ == '__main__':
    sys.exit(main())
