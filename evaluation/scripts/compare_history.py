#!/usr/bin/env python3
"""对比两次 LoCoMo 测试结果的脚本"""

import json
import sys
from pathlib import Path
from typing import Dict, Any


def load_test(test_id: str) -> Dict[str, Any]:
    """加载测试记录"""
    history_dir = Path(__file__).parent.parent / "history"
    test_file = history_dir / f"{test_id}.json"

    if not test_file.exists():
        raise FileNotFoundError(f"测试记录不存在: {test_file}")

    with open(test_file) as f:
        return json.load(f)


def compare_tests(baseline_id: str, current_id: str):
    """对比两次测试结果"""
    baseline = load_test(baseline_id)
    current = load_test(current_id)

    print("=" * 80)
    print(f"LoCoMo 测试对比")
    print("=" * 80)
    print()

    # 基本信息
    print("## 测试信息")
    print()
    print(f"**基线测试**: {baseline['test_name']}")
    print(f"  - ID: {baseline['test_id']}")
    print(f"  - Commit: {baseline['environment']['neuromemory_commit']}")
    print(f"  - 时间: {baseline['timestamp']}")
    print()
    print(f"**对比测试**: {current['test_name']}")
    print(f"  - ID: {current['test_id']}")
    print(f"  - Commit: {current['environment']['neuromemory_commit']}")
    print(f"  - 时间: {current['timestamp']}")
    print()

    # 优化措施
    if current.get('optimizations'):
        print("## 新增优化措施")
        print()
        for opt in current['optimizations']:
            print(f"  - {opt}")
        print()

    # 总体性能对比
    print("## 总体性能对比")
    print()

    baseline_overall = baseline['results']['overall']
    current_overall = current['results']['overall']

    print("| 指标 | 基线 | 当前 | 改进 | 提升幅度 |")
    print("|------|------|------|------|---------|")

    for metric in ['judge', 'f1', 'bleu1']:
        baseline_val = baseline_overall[metric]
        current_val = current_overall[metric]
        delta = current_val - baseline_val
        percent = (delta / baseline_val * 100) if baseline_val > 0 else 0

        print(f"| {metric.upper()} | {baseline_val:.3f} | {current_val:.3f} | "
              f"{delta:+.3f} | {percent:+.1f}% |")

    print()

    # 按类别对比
    print("## 按类别对比 (Judge 分数)")
    print()

    categories = {
        '1': 'Multi-hop',
        '2': 'Temporal',
        '3': 'Open-domain',
        '4': 'Single-hop'
    }

    print("| 类别 | 基线 | 当前 | 改进 | 提升幅度 |")
    print("|------|------|------|------|---------|")

    for cat_id, cat_name in categories.items():
        baseline_cat = baseline['results']['by_category'][cat_id]
        current_cat = current['results']['by_category'][cat_id]

        baseline_val = baseline_cat['judge']
        current_val = current_cat['judge']
        delta = current_val - baseline_val
        percent = (delta / baseline_val * 100) if baseline_val > 0 else 0

        count = current_cat['count']
        print(f"| {cat_name} ({count}题) | {baseline_val:.3f} | {current_val:.3f} | "
              f"{delta:+.3f} | {percent:+.1f}% |")

    print()

    # 性能对比
    if 'performance' in baseline and 'performance' in current:
        print("## 运行时间对比")
        print()

        baseline_perf = baseline['performance']
        current_perf = current['performance']

        print("| 阶段 | 基线 | 当前 | 加速 |")
        print("|------|------|------|------|")

        # Ingest
        baseline_ingest = baseline_perf.get('ingest_phase', {}).get('duration_hours')
        current_ingest = current_perf.get('ingest_phase', {}).get('duration_hours')
        if baseline_ingest and current_ingest:
            speedup = baseline_ingest / current_ingest
            print(f"| Ingest | {baseline_ingest:.1f}h | {current_ingest:.1f}h | {speedup:.1f}x |")

        # Total
        baseline_total = baseline_perf.get('total_duration_hours')
        current_total = current_perf.get('total_duration_hours')
        if baseline_total and current_total:
            speedup = baseline_total / current_total
            print(f"| Total | {baseline_total:.1f}h | {current_total:.1f}h | {speedup:.1f}x |")

        print()

    # 关键发现
    if current.get('key_findings'):
        print("## 关键发现")
        print()
        for finding in current['key_findings']:
            print(f"  - {finding}")
        print()

    # 遗留问题
    if current.get('issues'):
        print("## 遗留问题")
        print()
        for issue in current['issues']:
            print(f"  - {issue}")
        print()


def list_tests():
    """列出所有测试记录"""
    history_dir = Path(__file__).parent.parent / "history"
    index_file = history_dir / "index.json"

    if not index_file.exists():
        print("索引文件不存在")
        return

    with open(index_file) as f:
        index = json.load(f)

    print("可用的测试记录:")
    print()
    print("| 日期 | Test ID | Judge 分数 | 备注 |")
    print("|------|---------|-----------|------|")

    for test in index['tests']:
        print(f"| {test['date']} | {test['test_id']} | "
              f"{test['judge_score']:.3f} | {test.get('notes', '')} |")


def main():
    if len(sys.argv) == 1:
        list_tests()
        print()
        print("用法:")
        print("  python compare_history.py <baseline_id> <current_id>")
        print()
        print("示例:")
        print("  python compare_history.py 2025-02-15_baseline 2025-02-16_perf_opt")
        return

    if len(sys.argv) != 3:
        print("错误: 需要提供两个测试 ID")
        print("用法: python compare_history.py <baseline_id> <current_id>")
        sys.exit(1)

    baseline_id = sys.argv[1]
    current_id = sys.argv[2]

    try:
        compare_tests(baseline_id, current_id)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print()
        list_tests()
        sys.exit(1)


if __name__ == "__main__":
    main()
