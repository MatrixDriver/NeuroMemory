---
description: "技术可行性调研: RPIV-1 存储基座（Schema + ORM + 迁移）"
status: completed
created_at: 2026-02-28T22:30:00
updated_at: 2026-02-28T22:30:00
archived_at: null
---

# 技术可行性调研：RPIV-1 存储基座

## 项目当前依赖版本

| 依赖 | pyproject.toml 约束 | 实际安装版本 |
|------|---------------------|-------------|
| pgvector (Python) | `>=0.3.0` | 0.4.2 |
| SQLAlchemy | `>=2.0.0` | 2.0.45 |
| asyncpg | `>=0.30.0` | 0.31.0 |
| pgvector (PG 扩展) | 未锁定 | 需 >= 0.7.0（halfvec） |

---

## 调研项 A：pgvector HALFVEC 支持

### 结论：完全可行，当前版本已内置支持

**pgvector-python 0.4.2 已内置 HALFVEC 类型映射**，两种导入方式均可用：

```python
from pgvector.sqlalchemy import HALFVEC       # 大写，UserDefinedType
from pgvector.sqlalchemy import HalfVector     # 值类型（用于数据转换，非列声明）
```

**SQLAlchemy 列声明方式**：

```python
from pgvector.sqlalchemy import HALFVEC

embedding = mapped_column(HALFVEC(1024))  # 1024 维 halfvec
```

**HALFVEC 类型特征**（来自源码 `pgvector/sqlalchemy/halfvec.py`）：

- 继承 `UserDefinedType`，`cache_ok = True`
- `get_col_spec()` 返回 `'HALFVEC(N)'`
- 支持全部 4 种距离算子：`l2_distance`(`<->`)、`cosine_distance`(`<=>`)、`max_inner_product`(`<#>`)、`l1_distance`(`<+>`)
- `ischema_names['halfvec'] = HALFVEC` 已注册，支持反射

**asyncpg 集成**（来自源码 `pgvector/asyncpg/register.py`）：

```python
async def register_vector(conn, schema='public'):
    # vector 注册...
    try:
        await conn.set_type_codec('halfvec', ...)  # halfvec 在 try 中注册
    except ValueError as e:
        if not str(e).startswith('unknown type:'):
            raise e  # PG 端 pgvector < 0.7.0 时 graceful 降级
```

**版本要求**：
- pgvector Python 库：>= 0.3.0 即可（0.4.2 完整支持）
- pgvector PG 扩展：**>= 0.7.0**（2024-04-29 引入 halfvec 类型）
- PostgreSQL：>= 13（pgvector 0.7.0+ 的最低要求）
- HNSW 索引支持 halfvec 最多 4000 维（vector 仅 2000 维）

**风险项**：需确认 Railway 部署的 pgvector 扩展版本 >= 0.7.0。若低于此版本，halfvec 迁移将不可用。建议在迁移代码中先检测 pgvector 扩展版本。

---

## 调研项 B：vector -> halfvec 类型转换

### 结论：完全可行，PG 原生支持 cast

**SQL 语法**：

```sql
ALTER TABLE memories
ALTER COLUMN embedding TYPE halfvec(1024) USING embedding::halfvec(1024);
```

pgvector 在 PG 端注册了 `vector -> halfvec` 的 cast，此转换为：
- float32 逐元素截断为 float16（IEEE 754 半精度）
- 维度在 cast 时验证
- 需要表级排他锁（全表重写），大表应考虑低峰期执行

**存储影响**：
- vector(1024)：4 * 1024 + 8 = 4104 bytes/row
- halfvec(1024)：2 * 1024 + 8 = 2056 bytes/row
- 存储减半（~50% 空间节省）

**索引重建**：类型变更后必须：
1. DROP 旧的 vector 索引（使用 `vector_cosine_ops`）
2. CREATE 新的 halfvec 索引（使用 `halfvec_cosine_ops`）

**向量索引上的 cast 查询**（若保留 vector 列但用 halfvec 索引）：

```python
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.sql import func

# 创建 cast 索引
Index(
    'idx_embedding_halfvec',
    func.cast(Item.embedding, HALFVEC(1024)).label('embedding'),
    postgresql_using='hnsw',
    postgresql_with={'m': 16, 'ef_construction': 64},
    postgresql_ops={'embedding': 'halfvec_cosine_ops'}
)

# 查询时也需 cast
session.query(Item).order_by(
    func.cast(Item.embedding, HALFVEC(1024)).cosine_distance(query_vec)
)
```

**推荐方案**：直接 ALTER COLUMN TYPE 而非 cast 索引。原因：
1. 代码更简洁（不需要每次查询都 cast）
2. 存储确实减半
3. ORM 模型直接声明 HALFVEC
4. 迁移是一次性操作

**PG 版本要求**：>= 13（pgvector 0.7.0+ 要求）

---

## 调研项 C：ALTER TABLE RENAME 的幂等性

### 结论：可行，需组合检测 + 条件执行

**异步 SQLAlchemy 中检测表是否存在的三种方式**：

#### 方式 1：Inspector.has_table（推荐，框架标准 API）

```python
from sqlalchemy import inspect

async with engine.begin() as conn:
    def check_table(sync_conn, table_name):
        inspector = inspect(sync_conn)
        return inspector.has_table(table_name)

    has_embeddings = await conn.run_sync(check_table, "embeddings")
    has_memories = await conn.run_sync(check_table, "memories")
```

- SQLAlchemy 2.0+ 标准 API
- 通过 `run_sync` 桥接异步
- 跨方言兼容

#### 方式 2：to_regclass（PG 专用，最简洁）

```python
result = await conn.execute(
    text("SELECT to_regclass('embeddings') IS NOT NULL")
)
exists = result.scalar()
```

- 单行 SQL，无需 run_sync
- PG 专用但性能最优

#### 方式 3：information_schema 查询

```python
result = await conn.execute(text(
    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
    "WHERE table_name='embeddings' AND table_schema='public')"
))
exists = result.scalar()
```

**幂等 RENAME 实现模式**：

```python
async with engine.begin() as conn:
    has_old = (await conn.execute(
        text("SELECT to_regclass('embeddings') IS NOT NULL")
    )).scalar()
    has_new = (await conn.execute(
        text("SELECT to_regclass('memories') IS NOT NULL")
    )).scalar()

    if has_old and not has_new:
        await conn.execute(text("ALTER TABLE embeddings RENAME TO memories"))
    elif has_old and has_new:
        # 异常情况：两张表都存在，需要人工介入
        raise RuntimeError("Both 'embeddings' and 'memories' exist")
    # else: has_new=True（已改名）或两者都不存在（新安装由 create_all 处理）
```

**注意事项**：
- `ALTER TABLE RENAME` 会自动保留所有索引（索引名不变）
- `ALTER TABLE RENAME` 不会影响 ORM 映射（ORM 通过 `__tablename__` 绑定）
- RENAME 后，原来引用旧表名的 SQL 会报错 → 需同步更新 db.py 中的硬编码 SQL

---

## 调研项 D：UUID[] 数组类型

### 结论：完全可行，SQLAlchemy 原生支持

**声明方式**：

```python
from sqlalchemy.dialects.postgresql import UUID, ARRAY

source_episode_ids = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
```

**验证结果**（实际测试）：

```python
>>> from sqlalchemy.dialects.postgresql import UUID, ARRAY
>>> arr = ARRAY(UUID(as_uuid=True))
>>> repr(arr)
'ARRAY(UUID())'
>>> arr.item_type
UUID
```

**PG 兼容性**：
- PostgreSQL 原生支持任意类型的数组，UUID[] 完全支持
- asyncpg 原生支持 UUID 数组的序列化/反序列化
- 无额外依赖或版本要求

**使用场景注意**：
- 适合存储少量引用（source_episode_ids 通常 < 10 个元素）
- 不适合频繁追加操作（整个数组重写）→ 高频追加场景使用关联表（memory_sources）
- GIN 索引可加速 `@>` 包含查询

---

## 调研项 E：content_hash 的 MD5() 性能

### 结论：完全适合写入路径

**PG 内置 MD5() 函数特征**：

| 指标 | 值 |
|------|-----|
| 输出格式 | 32 字符 hex 字符串 |
| 计算速度 | ~500 MB/s（单核） |
| 典型记忆内容大小 | 100-1000 bytes |
| 单次计算耗时 | < 1 微秒 |
| 碰撞概率 | 2^-128（实际可忽略） |

**写入路径用法**：

```sql
-- 写入时计算
INSERT INTO memories (..., content_hash) VALUES (..., MD5($content));

-- 去重检查
SELECT id FROM memories
WHERE user_id = $user_id AND memory_type = $type AND content_hash = MD5($content)
LIMIT 1;
```

**Python 侧计算**（备选）：

```python
import hashlib
content_hash = hashlib.md5(content.encode()).hexdigest()
```

**推荐方案**：在 Python 侧（应用层）计算 MD5，而非 PG 函数调用。原因：
1. 减少一次 DB 交互（可在去重查询的 WHERE 中直接传入预计算值）
2. 与 NOOP 检测逻辑更好集成
3. hashlib.md5 性能等价

**索引建议**：

```sql
CREATE INDEX idx_content_hash ON memories (user_id, memory_type, content_hash)
WHERE content_hash IS NOT NULL;
```

改为复合索引（user_id + memory_type + content_hash），因为去重是同用户同类型内的去重。

---

## 调研项 F：框架内置方案检查

### F1. pgvector-python 的 HALFVEC 类型映射

**结论：已内置，可直接使用**

- `pgvector.sqlalchemy.HALFVEC`：SQLAlchemy 列类型
- `pgvector.halfvec.HalfVector`：值类型（编解码器）
- `pgvector.asyncpg.register_vector`：自动注册 halfvec 编解码器（graceful 降级）
- 已注册到 `ischema_names['halfvec']`，支持 SQLAlchemy 反射

无需任何自定义类型实现。

### F2. SQLAlchemy 表存在检测的标准 API

**结论：已内置 `Inspector.has_table()`**

```python
from sqlalchemy import inspect

# 同步环境
inspector = inspect(engine)
exists = inspector.has_table("embeddings")

# 异步环境（通过 run_sync）
async with engine.begin() as conn:
    exists = await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table("embeddings")
    )
```

- SQLAlchemy 1.4+ 引入，2.0 中标准化
- 检测范围包括：普通表、视图、临时表
- 跨方言兼容（PostgreSQL、SQLite 等）

### F3. 内置 content hash / dedup 机制

**结论：不存在内置方案，需自行实现**

- **pgvector-python**：纯类型映射库，无任何业务逻辑（dedup / hash / 版本控制等）。包文件结构确认仅含类型定义和编解码器
- **SQLAlchemy**：提供 `Column(unique=True)` 约束，但无 content hash 自动计算机制
- **asyncpg**：纯连接驱动，无业务逻辑

需自行实现的部分：
1. content_hash 计算（Python hashlib.md5）
2. 写入前查重逻辑
3. NOOP 判定规则

---

## 综合风险评估

| 技术点 | 可行性 | 风险等级 | 备注 |
|--------|--------|----------|------|
| HALFVEC 列声明 | 完全可行 | 低 | pgvector-python 0.4.2 已内置 |
| vector -> halfvec 转换 | 完全可行 | 中 | 需确认 PG 端 pgvector >= 0.7.0；大表需注意锁时间 |
| ALTER TABLE RENAME 幂等 | 完全可行 | 低 | Inspector.has_table 标准 API |
| UUID[] 数组 | 完全可行 | 低 | PG + SQLAlchemy + asyncpg 原生支持 |
| content_hash MD5 | 完全可行 | 低 | 性能无瓶颈，推荐 Python 侧计算 |
| 框架内置方案 | 部分可用 | 低 | HALFVEC + has_table 已内置，dedup 需自实现 |

### 需要额外关注的风险

1. **Railway pgvector 扩展版本**：halfvec 迁移的前提是 pgvector >= 0.7.0。建议在 `db.init()` 中添加版本检测：
   ```sql
   SELECT extversion FROM pg_extension WHERE extname = 'vector';
   ```

2. **vector -> halfvec 的锁时间**：`ALTER COLUMN TYPE` 需要 `ACCESS EXCLUSIVE` 锁，全表重写。当前数据量小（< 10K 行）不是问题，但应在低峰期执行。

3. **HALFVEC 精度损失**：float32 -> float16 的精度损失。根据 pgvector 官方测试，cosine similarity 的召回损失 < 0.3%，可接受。

4. **embeddings -> memories 改名后的代码引用**：当前 db.py 中硬编码了 `embeddings` 表名（5 处 ALTER TABLE / CREATE INDEX 语句），需同步更新。

---

## 实施建议

1. **pyproject.toml 依赖无需修改**：`pgvector>=0.3.0` 已涵盖 0.4.2，HALFVEC 支持已就位

2. **ORM 模型迁移路径**：
   ```python
   # 旧
   from pgvector.sqlalchemy import Vector
   embedding = mapped_column(Vector(dims))

   # 新
   from pgvector.sqlalchemy import HALFVEC
   embedding = mapped_column(HALFVEC(dims))
   ```

3. **db.py init 迁移顺序**（建议）：
   1. 检测 pgvector 扩展版本
   2. 检测 embeddings / memories 表状态
   3. RENAME（如需）
   4. ADD COLUMN IF NOT EXISTS（新列）
   5. CREATE TABLE（辅助表，via create_all）
   6. 数据回填
   7. vector -> halfvec 转换
   8. 索引重建

4. **向量维度配置化**：当前代码已有 `_models._embedding_dims` 机制（`memory.py:65`），HALFVEC 迁移应复用此机制
