# 快速发布到 PyPI

## 一次性配置（仅首次）

### 1. 安装工具
```bash
pip install build twine
```

### 2. 配置 PyPI Token

创建 `~/.pypirc` 文件：
```bash
nano ~/.pypirc
```

填入以下内容（替换为你的 token）：
```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...你的完整token...

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9yZw...测试环境token（可选）...
```

保护文件权限：
```bash
chmod 600 ~/.pypirc
```

### 3. 完善项目信息

编辑 `pyproject.toml`，替换：
- `authors` 中的邮箱
- `project.urls` 中的 GitHub 链接

---

## 每次发布（3 步）

### 步骤 1: 更新版本号
编辑 `pyproject.toml`：
```toml
version = "2.0.1"  # 改为新版本号
```

### 步骤 2: 提交到 Git（可选但推荐）
```bash
git add pyproject.toml
git commit -m "chore: bump version to 2.0.1"
git tag v2.0.1
git push && git push --tags
```

### 步骤 3: 运行发布脚本
```bash
./scripts/publish.sh
```

**或者手动执行**：
```bash
rm -rf dist/ && python -m build && python -m twine upload dist/*
```

---

## 验证

等待 1-2 分钟后：
```bash
pip install neuromem==2.0.1
```

访问查看：https://pypi.org/project/neuromem/

---

## 常见错误

**"File already exists"** → 增加版本号，PyPI 不允许覆盖

**"Invalid or non-existent authentication"** → 检查 `~/.pypirc` 中的 token 是否正确

**导入失败** → 确保 `neuromem/__init__.py` 存在并正确导出

---

## 完整文档

详细说明请查看：[PUBLISH.md](./PUBLISH.md)
