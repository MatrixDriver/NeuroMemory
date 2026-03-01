#!/usr/bin/env python3
"""
验证测试数据的完整性和一致性

用于在测试的每个阶段开始前检查前置条件，避免使用错误的数据运行测试。
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from typing import Dict, List, Tuple
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.config import EvalConfig


def check_database_connection(db_url: str) -> bool:
    """检查数据库连接"""
    try:
        engine = create_engine(db_url.replace('+asyncpg', ''))
        with engine.connect():
            return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


def get_memory_stats(db_url: str) -> Dict[str, int]:
    """获取每个 user 的记忆数量"""
    engine = create_engine(db_url.replace('+asyncpg', ''))
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, COUNT(*) as count
            FROM memories
            GROUP BY user_id
            ORDER BY user_id
        """))
        return {row[0]: row[1] for row in result}


def get_conversation_stats(db_url: str) -> Dict[str, int]:
    """获取每个 user 的会话数量"""
    engine = create_engine(db_url.replace('+asyncpg', ''))
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, COUNT(*) as count
            FROM conversation_sessions
            GROUP BY user_id
            ORDER BY user_id
        """))
        return {row[0]: row[1] for row in result}


def load_expected_users(benchmark: str, data_path: str) -> List[Tuple[int, str, str]]:
    """加载预期的 user_id 列表"""
    with open(data_path, 'r') as f:
        data = json.load(f)

    if benchmark == 'locomo':
        # LoCoMo format: Caroline_0, Melanie_0, ...
        users = []
        for idx, item in enumerate(data):
            conv = item['conversation']
            speaker_a = conv['speaker_a']
            speaker_b = conv['speaker_b']
            users.append((idx, f"{speaker_a}_{idx}", f"{speaker_b}_{idx}"))
        return users
    elif benchmark == 'longmemeval':
        # LongMemEval format: lme_xxxxx
        # TODO: implement if needed
        return []
    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")


def validate_ingest_prereq(cfg: EvalConfig) -> bool:
    """验证 ingest 阶段的前置条件"""
    print("🔍 验证 Ingest 阶段前置条件...")

    # 1. 检查数据库连接
    if not check_database_connection(cfg.database_url):
        return False
    print("✅ 数据库连接正常")

    # 2. 检查数据文件存在
    if not Path(cfg.locomo_data_path).exists():
        print(f"❌ 数据文件不存在: {cfg.locomo_data_path}")
        return False
    print(f"✅ 数据文件存在: {cfg.locomo_data_path}")

    # 3. 检查是否有残留数据
    memory_stats = get_memory_stats(cfg.database_url)
    conv_stats = get_conversation_stats(cfg.database_url)

    if memory_stats or conv_stats:
        print("⚠️  数据库中存在残留数据:")
        print(f"   - Embeddings: {len(memory_stats)} users, {sum(memory_stats.values())} total")
        print(f"   - Conversations: {len(conv_stats)} users, {sum(conv_stats.values())} sessions")
        print("\n建议：运行 'python -m evaluation.cli locomo --clean' 清理数据")
        # 不返回 False，只是警告
    else:
        print("✅ 数据库为空，可以开始 ingest")

    return True


def validate_query_prereq(cfg: EvalConfig, benchmark: str) -> bool:
    """验证 query 阶段的前置条件"""
    print("🔍 验证 Query 阶段前置条件...")

    # 1. 检查数据库连接
    if not check_database_connection(cfg.database_url):
        return False
    print("✅ 数据库连接正常")

    # 2. 加载预期的 user_id
    expected_users = load_expected_users(benchmark, cfg.locomo_data_path)
    print(f"📋 预期 {len(expected_users)} 个对话，{len(expected_users) * 2} 个用户")

    # 3. 检查实际的记忆数据
    memory_stats = get_memory_stats(cfg.database_url)
    conv_stats = get_conversation_stats(cfg.database_url)

    if not memory_stats:
        print("❌ 数据库中没有记忆数据！")
        print("   请先运行 ingest 阶段: python -m evaluation.cli locomo --phase ingest")
        return False

    # 4. 验证 user_id 格式和完整性
    expected_user_ids = set()
    for conv_idx, user_a, user_b in expected_users:
        expected_user_ids.add(user_a)
        expected_user_ids.add(user_b)

    actual_user_ids = set(memory_stats.keys())

    missing = expected_user_ids - actual_user_ids
    extra = actual_user_ids - expected_user_ids

    if missing:
        print(f"❌ 缺少 {len(missing)} 个用户的记忆数据:")
        for uid in sorted(list(missing)[:10]):
            print(f"   - {uid}")
        if len(missing) > 10:
            print(f"   ... 还有 {len(missing) - 10} 个")
        return False

    if extra:
        print(f"⚠️  数据库中有 {len(extra)} 个额外的用户（可能是其他测试残留）:")
        for uid in sorted(list(extra)[:5]):
            print(f"   - {uid} ({memory_stats.get(uid, 0)} memories)")
        if len(extra) > 5:
            print(f"   ... 还有 {len(extra) - 5} 个")

    # 5. 检查每个用户的记忆数量
    print("\n📊 记忆数据统计:")
    for conv_idx, user_a, user_b in expected_users[:5]:
        mem_a = memory_stats.get(user_a, 0)
        mem_b = memory_stats.get(user_b, 0)
        status_a = "✅" if mem_a > 0 else "❌"
        status_b = "✅" if mem_b > 0 else "❌"
        print(f"   Conv {conv_idx}: {status_a} {user_a} ({mem_a}), {status_b} {user_b} ({mem_b})")

    if len(expected_users) > 5:
        print(f"   ... 还有 {len(expected_users) - 5} 个对话")

    # 6. 检查是否有 conv 的记忆数为 0
    zero_memory_convs = []
    for conv_idx, user_a, user_b in expected_users:
        if memory_stats.get(user_a, 0) == 0 or memory_stats.get(user_b, 0) == 0:
            zero_memory_convs.append(conv_idx)

    if zero_memory_convs:
        print(f"\n❌ 有 {len(zero_memory_convs)} 个对话的记忆数为 0:")
        print(f"   Conv 索引: {zero_memory_convs}")
        print("   这会导致 query 结果不准确！")
        return False

    print(f"\n✅ 所有 {len(expected_users)} 个对话都有记忆数据")
    print(f"   总记忆数: {sum(memory_stats.values())}")
    print(f"   平均每个用户: {sum(memory_stats.values()) // len(memory_stats)}")

    return True


def validate_evaluate_prereq(cfg: EvalConfig) -> bool:
    """验证 evaluate 阶段的前置条件"""
    print("🔍 验证 Evaluate 阶段前置条件...")

    # 1. 检查 query 结果文件
    results_path = Path(cfg.results_dir) / "locomo_query_checkpoint.json"
    if not results_path.exists():
        print(f"❌ Query 结果文件不存在: {results_path}")
        print("   请先运行 query 阶段")
        return False

    # 2. 检查结果数量
    with open(results_path, 'r') as f:
        checkpoint = json.load(f)

    results = checkpoint.get('results', [])
    if not results:
        print("❌ Query 结果为空！")
        return False

    print(f"✅ Query 结果文件存在，包含 {len(results)} 个结果")

    # 3. 检查结果的完整性（应该有 1540 个问题）
    if len(results) < 1540:
        print(f"⚠️  Query 结果不完整: {len(results)}/1540")

    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="验证测试数据的完整性")
    parser.add_argument('phase', choices=['ingest', 'query', 'evaluate'],
                        help='要验证的阶段')
    parser.add_argument('--benchmark', default='locomo',
                        help='Benchmark 名称')
    args = parser.parse_args()

    cfg = EvalConfig()

    print(f"\n{'='*60}")
    print(f"测试数据验证 - {args.phase.upper()} 阶段")
    print(f"{'='*60}\n")

    if args.phase == 'ingest':
        success = validate_ingest_prereq(cfg)
    elif args.phase == 'query':
        success = validate_query_prereq(cfg, args.benchmark)
    elif args.phase == 'evaluate':
        success = validate_evaluate_prereq(cfg)
    else:
        print(f"❌ 未知阶段: {args.phase}")
        sys.exit(1)

    print(f"\n{'='*60}")
    if success:
        print(f"✅ {args.phase.upper()} 阶段前置条件验证通过")
        print(f"{'='*60}\n")
        sys.exit(0)
    else:
        print(f"❌ {args.phase.upper()} 阶段前置条件验证失败")
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
