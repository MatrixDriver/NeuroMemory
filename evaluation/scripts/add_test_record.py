#!/usr/bin/env python3
"""添加新的测试记录到历史中"""

import json
import sys
from pathlib import Path
from datetime import datetime


def get_git_commit():
    """获取当前 git commit"""
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%H'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()[:8]
    except:
        return "unknown"


def get_git_branch():
    """获取当前 git branch"""
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except:
        return "unknown"


def create_test_record(
    test_id: str,
    test_name: str,
    results_file: str,
    optimizations: list,
    notes: str = ""
):
    """创建新的测试记录"""

    # 读取测试结果
    results_path = Path(results_file)
    if not results_path.exists():
        raise FileNotFoundError(f"结果文件不存在: {results_file}")

    with open(results_path) as f:
        results = json.load(f)

    # 获取 git 信息
    commit = get_git_commit()
    branch = get_git_branch()

    # 创建记录
    record = {
        "test_id": test_id,
        "test_name": test_name,
        "timestamp": datetime.now().isoformat(),
        "benchmark": "locomo",
        "dataset": "locomo10.json",

        "environment": {
            "neuromem_commit": commit,
            "neuromem_branch": branch,
            "neuromem_version": "v0.2.x-dev",
            "eval_commit": commit,
            "database": {
                "type": "postgresql",
                "version": "16.x",
                "host": "localhost:5433",
                "isolation": "dedicated_container",
                "extensions": ["pgvector", "age"]
            },
            "embedding": {
                "provider": "siliconflow",
                "model": "BAAI/bge-m3",
                "dimensions": 1024
            },
            "llm": {
                "provider": "deepseek",
                "model": "deepseek-chat"
            },
            "judge": {
                "provider": "deepseek",
                "model": "deepseek-chat"
            }
        },

        "optimizations": optimizations,

        "performance": {
            "ingest_phase": {
                "duration_hours": None,
                "note": "请手动填写"
            },
            "query_phase": {
                "duration_hours": None,
                "questions": results['total_questions']
            },
            "evaluate_phase": {
                "duration_hours": None
            },
            "total_duration_hours": None
        },

        "results": results,

        "key_findings": [],
        "issues": [],
        "notes": notes
    }

    # 保存记录
    history_dir = Path(__file__).parent.parent / "history"
    output_file = history_dir / f"{test_id}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"✅ 测试记录已创建: {output_file}")
    print()
    print("下一步:")
    print("1. 编辑文件，补充 performance 信息（耗时）")
    print("2. 填写 key_findings 和 issues")
    print(f"3. 更新 evaluation/history/index.json，添加此测试")
    print()
    print("示例:")
    print(f"  vim {output_file}")


def main():
    if len(sys.argv) < 4:
        print("用法: python add_test_record.py <test_id> <test_name> <results_file> [optimizations...]")
        print()
        print("示例:")
        print('  python add_test_record.py \\')
        print('    2025-02-20_graph_opt \\')
        print('    "Graph Memory Optimization" \\')
        print('    evaluation/results/locomo_results.json \\')
        print('    "优化图谱构建" "改进多跳推理"')
        sys.exit(1)

    test_id = sys.argv[1]
    test_name = sys.argv[2]
    results_file = sys.argv[3]
    optimizations = sys.argv[4:] if len(sys.argv) > 4 else []

    try:
        create_test_record(test_id, test_name, results_file, optimizations)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
