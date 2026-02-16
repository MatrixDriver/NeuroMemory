#!/bin/bash
#
# 完整的 LoCoMo 测试运行脚本
# 自动化整个测试流程并包含验证检查
#

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
BENCHMARK="locomo"
TEST_NAME="${1:-auto_$(date +%Y%m%d_%H%M%S)}"
RESULTS_DIR="evaluation/results"
HISTORY_DIR="evaluation/history"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 分隔线
print_separator() {
    echo "=================================================================="
}

# 阶段标题
print_phase() {
    print_separator
    echo -e "${BLUE}$1${NC}"
    print_separator
}

# 错误处理
trap 'log_error "测试脚本执行失败！"; exit 1' ERR

# 开始测试
print_separator
echo -e "${GREEN}LoCoMo 完整测试流程${NC}"
echo "测试名称: $TEST_NAME"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
print_separator
echo ""

# ============================================================================
# 阶段 0: 环境检查
# ============================================================================
print_phase "阶段 0: 环境检查"

log_info "检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    log_error "Python3 未安装"
    exit 1
fi
log_success "Python3 已安装: $(python3 --version)"

log_info "检查数据库连接..."
if ! python3 evaluation/scripts/validate_test_data.py ingest; then
    log_error "数据库连接检查失败"
    exit 1
fi

log_info "检查 Git 状态..."
GIT_COMMIT=$(git rev-parse --short HEAD)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_DIRTY=$(git diff --quiet && echo "clean" || echo "dirty")
log_info "Git: $GIT_BRANCH @ $GIT_COMMIT ($GIT_DIRTY)"

if [ "$GIT_DIRTY" = "dirty" ]; then
    log_warning "工作目录有未提交的更改！"
    read -p "是否继续测试？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "测试已取消"
        exit 0
    fi
fi

echo ""

# ============================================================================
# 阶段 1: 数据清理
# ============================================================================
print_phase "阶段 1: 数据清理"

log_info "清理旧的测试数据..."
read -p "是否清空数据库？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "执行数据库清理..."
    python3 -m evaluation.cli locomo --clean
    log_success "数据库已清理"
else
    log_warning "跳过数据库清理"
fi

log_info "删除旧的 checkpoint 文件..."
rm -f ${RESULTS_DIR}/locomo_ingest_checkpoint.json
rm -f ${RESULTS_DIR}/locomo_query_checkpoint.json
rm -f ${RESULTS_DIR}/locomo_evaluate_checkpoint.json
log_success "Checkpoint 文件已删除"

echo ""

# ============================================================================
# 阶段 2: Ingest (记忆提取)
# ============================================================================
print_phase "阶段 2: Ingest (记忆提取)"

log_info "验证 ingest 前置条件..."
if ! python3 evaluation/scripts/validate_test_data.py ingest; then
    log_error "Ingest 前置条件验证失败"
    exit 1
fi

log_info "开始 ingest 阶段..."
INGEST_START=$(date +%s)
python3 -m evaluation.cli locomo --phase ingest 2>&1 | tee ${RESULTS_DIR}/ingest_${TEST_NAME}.log
INGEST_END=$(date +%s)
INGEST_DURATION=$((INGEST_END - INGEST_START))

log_success "Ingest 阶段完成，耗时: $((INGEST_DURATION / 60)) 分钟 $((INGEST_DURATION % 60)) 秒"

# 验证 ingest 结果
log_info "验证 ingest 结果..."
python3 -c "
from sqlalchemy import create_engine, text
import os

db_url = os.environ.get('DATABASE_URL', 'postgresql://neuromemory:neuromemory@localhost:5433/neuromemory_eval')
engine = create_engine(db_url)

with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(DISTINCT user_id) FROM embeddings'))
    user_count = result.scalar()
    result = conn.execute(text('SELECT COUNT(*) FROM embeddings'))
    total_memories = result.scalar()

    print(f'✅ Ingest 结果: {user_count} 个用户, {total_memories} 条记忆')

    if user_count == 0:
        print('❌ 错误：没有提取到任何记忆！')
        exit(1)
"

echo ""

# ============================================================================
# 阶段 3: Query (问题回答)
# ============================================================================
print_phase "阶段 3: Query (问题回答)"

log_info "验证 query 前置条件..."
if ! python3 evaluation/scripts/validate_test_data.py query; then
    log_error "Query 前置条件验证失败"
    log_error "请检查 ingest 阶段是否成功完成"
    exit 1
fi

log_info "开始 query 阶段..."
QUERY_START=$(date +%s)
python3 -m evaluation.cli locomo --phase query 2>&1 | tee ${RESULTS_DIR}/query_${TEST_NAME}.log
QUERY_END=$(date +%s)
QUERY_DURATION=$((QUERY_END - QUERY_START))

log_success "Query 阶段完成，耗时: $((QUERY_DURATION / 60)) 分钟 $((QUERY_DURATION % 60)) 秒"

# 验证 query 结果
log_info "验证 query 结果..."
python3 -c "
import json
with open('evaluation/results/locomo_query_checkpoint.json', 'r') as f:
    checkpoint = json.load(f)
    result_count = len(checkpoint.get('results', []))
    print(f'✅ Query 结果: {result_count} 个问题')

    if result_count < 1540:
        print(f'⚠️  警告：结果不完整（预期 1540 个）')
"

echo ""

# ============================================================================
# 阶段 4: Evaluate (LLM Judge 评分)
# ============================================================================
print_phase "阶段 4: Evaluate (LLM Judge 评分)"

log_info "验证 evaluate 前置条件..."
if ! python3 evaluation/scripts/validate_test_data.py evaluate; then
    log_error "Evaluate 前置条件验证失败"
    exit 1
fi

log_info "开始 evaluate 阶段..."
EVAL_START=$(date +%s)
python3 -m evaluation.cli locomo --phase evaluate 2>&1 | tee ${RESULTS_DIR}/evaluate_${TEST_NAME}.log
EVAL_END=$(date +%s)
EVAL_DURATION=$((EVAL_END - EVAL_START))

log_success "Evaluate 阶段完成，耗时: $((EVAL_DURATION / 60)) 分钟 $((EVAL_DURATION % 60)) 秒"

echo ""

# ============================================================================
# 阶段 5: 生成测试报告
# ============================================================================
print_phase "阶段 5: 生成测试报告"

log_info "创建测试记录..."
python3 evaluation/scripts/add_test_record.py \
    "$TEST_NAME" \
    "Complete test run on $GIT_BRANCH @ $GIT_COMMIT" \
    ${RESULTS_DIR}/locomo_results.json

log_info "更新测试记录的性能数据..."
# TODO: 自动填充 performance 数据

log_success "测试记录已创建: ${HISTORY_DIR}/${TEST_NAME}.json"

# 显示测试结果
log_info "测试结果摘要:"
python3 -c "
import json
with open('evaluation/results/locomo_results.json', 'r') as f:
    results = json.load(f)
    overall = results['overall']
    print(f'  Judge Score: {overall[\"judge\"]:.4f}')
    print(f'  F1 Score:    {overall[\"f1\"]:.4f}')
    print(f'  BLEU-1:      {overall[\"bleu1\"]:.4f}')
    print()
    print('按类别:')
    for cat_id, cat_data in sorted(results['by_category'].items()):
        print(f'  Category {cat_id}: Judge={cat_data[\"judge\"]:.4f}, F1={cat_data[\"f1\"]:.4f}, Count={cat_data[\"count\"]}')
"

echo ""

# ============================================================================
# 测试完成
# ============================================================================
TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - INGEST_START))

print_separator
log_success "测试完成！"
echo "测试名称: $TEST_NAME"
echo "总耗时: $((TOTAL_DURATION / 3600)) 小时 $(((TOTAL_DURATION % 3600) / 60)) 分钟"
echo ""
echo "各阶段耗时:"
echo "  Ingest:   $((INGEST_DURATION / 60)) 分钟"
echo "  Query:    $((QUERY_DURATION / 60)) 分钟"
echo "  Evaluate: $((EVAL_DURATION / 60)) 分钟"
echo ""
echo "结果文件:"
echo "  - ${RESULTS_DIR}/locomo_results.json"
echo "  - ${HISTORY_DIR}/${TEST_NAME}.json"
print_separator

exit 0
