# LoCoMo 测试指南

## 测试流程改进

本指南记录了为避免数据不一致问题而进行的测试流程改进。

### 问题总结

**2025-02-17 测试中发现的问题**：
1. ❌ 跳过了 ingest 阶段，直接运行 query
2. ❌ 数据库中使用了其他测试残留的数据
3. ❌ 没有验证记忆数据与测试数据的对应关系
4. ❌ 导致测试结果完全无效（性能下降 32.7%）

### 改进措施

#### 1. 数据验证脚本 (`validate_test_data.py`)

**功能**：在每个阶段开始前验证前置条件

**用法**：
```bash
# 验证 ingest 前置条件
python evaluation/scripts/validate_test_data.py ingest

# 验证 query 前置条件（会检查记忆数据是否存在）
python evaluation/scripts/validate_test_data.py query

# 验证 evaluate 前置条件（会检查 query 结果）
python evaluation/scripts/validate_test_data.py evaluate
```

**检查内容**：

**Ingest 阶段**：
- ✅ 数据库连接
- ✅ 数据文件存在
- ⚠️ 残留数据警告

**Query 阶段**：
- ✅ 数据库连接
- ✅ 预期的 user_id 是否存在
- ✅ 每个 conversation 是否都有记忆数据
- ❌ 检测记忆数为 0 的 conversation
- ⚠️ 检测不匹配的 user_id（如 `lme_` 前缀）

**Evaluate 阶段**：
- ✅ Query 结果文件存在
- ✅ 结果数量正确（1540 个）

#### 2. 完整测试脚本 (`run_full_test.sh`)

**功能**：自动化完整测试流程，包含所有验证检查

**用法**：
```bash
# 运行完整测试（自动生成测试名称）
./evaluation/scripts/run_full_test.sh

# 指定测试名称
./evaluation/scripts/run_full_test.sh my_test_name
```

**执行流程**：
1. ✅ 环境检查（Python、数据库、Git 状态）
2. 🧹 数据清理（可选）
3. 📥 Ingest 阶段 + 验证
4. 🔍 Query 阶段 + 验证
5. 📊 Evaluate 阶段 + 验证
6. 📝 生成测试报告

**特性**：
- 自动验证每个阶段的前置条件
- 失败时立即退出，不继续执行
- 记录每个阶段的日志
- 自动计算耗时
- 生成完整的测试报告

### 正确的测试流程

#### 方式一：使用自动化脚本（推荐）

```bash
# 1. 运行完整测试
./evaluation/scripts/run_full_test.sh my_test_2025_02_17

# 2. 查看结果
cat evaluation/history/my_test_2025_02_17.json
```

#### 方式二：手动执行（带验证）

```bash
# 1. 清理数据库
python -m evaluation.cli locomo --clean

# 2. Ingest 阶段
python evaluation/scripts/validate_test_data.py ingest
python -m evaluation.cli locomo --phase ingest

# 3. Query 阶段
python evaluation/scripts/validate_test_data.py query  # 关键！
python -m evaluation.cli locomo --phase query

# 4. Evaluate 阶段
python evaluation/scripts/validate_test_data.py evaluate
python -m evaluation.cli locomo --phase evaluate

# 5. 生成测试记录
python evaluation/scripts/add_test_record.py \
    "test_name" \
    "Test description" \
    evaluation/results/locomo_results.json
```

### 数据完整性检查清单

**运行测试前**：
- [ ] 数据库连接正常
- [ ] 数据库已清空或确认数据匹配
- [ ] Git 状态已记录
- [ ] 环境变量配置正确

**Ingest 完成后**：
- [ ] 所有 conversation 的 user_id 存在
- [ ] 每个 user_id 都有记忆数据
- [ ] 记忆总数合理（通常 >1000）

**Query 完成后**：
- [ ] 结果数量正确（1540 个）
- [ ] 没有大量失败的问题
- [ ] Checkpoint 文件存在

**Evaluate 完成后**：
- [ ] 结果文件生成
- [ ] 分数合理（Judge > 0.1）
- [ ] 所有类别都有数据

### 常见问题排查

#### 问题 1：Query 阶段性能异常低

**症状**：Judge Score < 0.2，大量 "No information" 回答

**排查步骤**：
```bash
# 检查记忆数据
python3 -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://neuromemory:neuromemory@localhost:5433/neuromemory_eval')
with engine.connect() as conn:
    result = conn.execute(text('SELECT user_id, COUNT(*) FROM embeddings GROUP BY user_id'))
    for row in result:
        print(f'{row[0]}: {row[1]} memories')
"

# 检查是否有 LoCoMo 格式的 user_id
# 应该看到: Caroline_0, Melanie_0, Jon_1, Gina_1, ...
# 而不是: lme_xxxxx
```

**解决方案**：
1. 数据库清空：`python -m evaluation.cli locomo --clean`
2. 重新运行 ingest：`python -m evaluation.cli locomo --phase ingest`

#### 问题 2：Query 阶段部分 conversation 失败

**症状**：某些 conversation 的问题大量失败或返回 "Unknown"

**排查步骤**：
```bash
# 检查每个 conversation 的记忆数
python evaluation/scripts/validate_test_data.py query
# 会显示哪些 conversation 的记忆数为 0
```

**解决方案**：
1. 检查 ingest 阶段日志，查看是否有错误
2. 确认新代码的 reflect() 方法是否正常工作
3. 重新运行完整测试

#### 问题 3：数据库残留数据

**症状**：validation 脚本警告有残留数据

**排查步骤**：
```bash
# 查看残留数据的创建时间
python3 -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://neuromemory:neuromemory@localhost:5433/neuromemory_eval')
with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT user_id, COUNT(*),
               MIN(created_at) as first,
               MAX(created_at) as last
        FROM embeddings
        GROUP BY user_id
    '''))
    for row in result:
        print(f'{row[0]}: {row[1]} memories ({row[2]} ~ {row[3]})')
"
```

**解决方案**：
1. 清空数据库：`python -m evaluation.cli locomo --clean`
2. 或使用独立的数据库容器

### 最佳实践

1. **每次测试前清空数据库**
   ```bash
   python -m evaluation.cli locomo --clean
   ```

2. **使用验证脚本检查前置条件**
   ```bash
   python evaluation/scripts/validate_test_data.py query
   ```

3. **记录 Git 状态**
   - 提交代码更改
   - 记录 commit hash
   - 在测试记录中注明

4. **保存完整日志**
   ```bash
   python -m evaluation.cli locomo --phase ingest 2>&1 | tee ingest.log
   ```

5. **验证测试结果**
   - 检查记忆数量是否合理
   - 检查分数是否在预期范围
   - 对比历史测试结果

### 代码改进建议

**未来可以考虑的改进**：

1. **在 CLI 中集成验证**
   ```python
   # 在 locomo.py 的每个 phase 开始前自动调用验证
   if phase == 'query':
       validate_query_prereq(cfg, 'locomo')
   ```

2. **Checkpoint 包含测试元数据**
   ```json
   {
     "test_id": "test_name",
     "git_commit": "8a8188f1",
     "timestamp": "2025-02-17T14:57:00",
     "results": [...]
   }
   ```

3. **自动检测数据不匹配**
   - Query 阶段检测到记忆数为 0 时立即报错
   - 而不是继续执行并产生无效结果

4. **数据隔离**
   - 每次测试使用独特的 user_id 前缀
   - 例如：`test_20250217_Caroline_0`

5. **测试报告增强**
   - 记录每个 conv 的记忆数/问题数
   - 自动检测异常并标记
   - 生成数据质量报告

### 总结

**核心原则**：
- ✅ **验证优先**：每个阶段开始前验证前置条件
- ✅ **数据清理**：每次测试前清空数据库
- ✅ **自动化**：使用脚本避免手动错误
- ✅ **日志记录**：保存完整日志便于排查
- ✅ **结果验证**：测试完成后验证数据完整性

**避免的错误**：
- ❌ 跳过阶段
- ❌ 使用残留数据
- ❌ 不验证前置条件
- ❌ 忽略警告信息
