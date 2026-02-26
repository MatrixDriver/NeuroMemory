# 发布 neuromem 到 PyPI 指南

## 一次性准备工作

### 1. 安装发布工具

```bash
pip install build twine
```

### 2. 配置 PyPI API Token

创建 `~/.pypirc` 文件（**推荐方式**，最安全）：

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...你的完整API-token...
```

**文件权限**（重要！保护 token 安全）：
```bash
chmod 600 ~/.pypirc
```

或者使用环境变量（临时方式）：
```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmc...
```

---

## 发布流程（每次发布）

### 步骤 1: 更新版本号

编辑 `pyproject.toml`：
```toml
version = "2.0.1"  # 增加版本号
```

版本号规则（语义化版本）：
- `2.0.0` → `2.0.1` - Bug 修复（patch）
- `2.0.0` → `2.1.0` - 新功能，向后兼容（minor）
- `2.0.0` → `3.0.0` - 破坏性更改（major）

### 步骤 2: 提交代码

```bash
git add pyproject.toml
git commit -m "chore: bump version to 2.0.1"
git tag v2.0.1  # 可选，但推荐
git push && git push --tags
```

### 步骤 3: 清理旧构建（如果存在）

```bash
rm -rf dist/ build/ *.egg-info/
```

### 步骤 4: 构建包

```bash
python -m build
```

这会在 `dist/` 目录生成两个文件：
- `neuromem-2.0.1.tar.gz` - 源码分发包
- `neuromem-2.0.1-py3-none-any.whl` - Wheel 二进制包

### 步骤 5: 上传到 PyPI

```bash
python -m twine upload dist/*
```

**成功输出示例**：
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading neuromem-2.0.1-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 50.0/50.0 kB
Uploading neuromem-2.0.1.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45.0/45.0 kB

View at:
https://pypi.org/project/neuromem/2.0.1/
```

### 步骤 6: 验证安装

等待 1-2 分钟后：

```bash
# 在新环境中测试
pip install neuromem==2.0.1

# 或者升级现有安装
pip install --upgrade neuromem
```

---

## 一键发布脚本（可选）

创建 `scripts/publish.sh`：

```bash
#!/bin/bash
set -e

# 检查是否有未提交的更改
if [[ -n $(git status -s) ]]; then
    echo "❌ 有未提交的更改，请先提交"
    exit 1
fi

# 读取当前版本
VERSION=$(grep "^version" pyproject.toml | cut -d'"' -f2)
echo "📦 当前版本: $VERSION"

# 清理旧构建
rm -rf dist/ build/ *.egg-info/
echo "🧹 清理完成"

# 构建
echo "🔨 构建中..."
python -m build

# 上传
echo "📤 上传到 PyPI..."
python -m twine upload dist/*

echo "✅ 发布成功！"
echo "🔗 查看: https://pypi.org/project/neuromem/$VERSION/"
```

使用：
```bash
chmod +x scripts/publish.sh
./scripts/publish.sh
```

---

## 使用 TestPyPI 测试（推荐先测试）

在正式发布前，可以先上传到测试环境：

### 1. 配置 TestPyPI token

在 `~/.pypirc` 添加：
```ini
[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9yZw...你的TestPyPI-token...
```

### 2. 上传到 TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

### 3. 从 TestPyPI 安装测试

```bash
pip install --index-url https://test.pypi.org/simple/ neuromem
```

---

## 常见问题

### Q1: 上传失败 "File already exists"
**原因**：PyPI 不允许覆盖已发布的版本。

**解决**：增加版本号后重新构建上传。

### Q2: 导入错误 "No module named neuromem"
**检查**：
```bash
# 确认包结构正确
python -m build
tar -tzf dist/neuromem-*.tar.gz | grep neuromem/

# 应该看到 neuromem/__init__.py 等文件
```

### Q3: 缺少依赖
**确认** `pyproject.toml` 中 `dependencies` 列表完整。

### Q4: README 在 PyPI 上显示不正确
**确认** `README.md` 使用标准 Markdown 格式。

---

## 自动化发布（GitHub Actions）

创建 `.github/workflows/publish.yml`：

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install build tools
        run: pip install build twine

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: python -m twine upload dist/*
```

**设置**：
1. 在 GitHub repo 的 Settings → Secrets → Actions
2. 添加 secret `PYPI_API_TOKEN`，值为你的 PyPI token
3. 以后只需在 GitHub 上创建 Release，自动触发发布

---

## 版本管理最佳实践

1. **遵循语义化版本**：`MAJOR.MINOR.PATCH`
2. **保持 CHANGELOG**：记录每个版本的变更
3. **Git tag 对应版本**：`git tag v2.0.1`
4. **先测试再发布**：本地测试 → TestPyPI → 正式 PyPI
5. **不要删除 PyPI 版本**：有问题立即发布修复版本

---

## 检查清单

发布前确认：

- [ ] 更新了版本号
- [ ] 更新了 CHANGELOG.md（如果有）
- [ ] 所有测试通过（`pytest tests/`）
- [ ] README.md 文档最新
- [ ] 提交了所有更改到 git
- [ ] 清理了 `dist/` 目录
- [ ] 构建成功（`python -m build`）
- [ ] 可选：先上传到 TestPyPI 测试

---

## 快速参考

```bash
# 完整发布流程（一行命令）
rm -rf dist/ build/ *.egg-info/ && \
python -m build && \
python -m twine upload dist/*

# 上传到 TestPyPI
python -m twine upload --repository testpypi dist/*

# 检查包内容
tar -tzf dist/neuromem-*.tar.gz
```

---

## 首次发布注意事项

### 1. 确保包名可用

访问 https://pypi.org/project/neuromem/ 查看是否已被占用。

### 2. 完善 pyproject.toml

确保填写了：
- `authors` - 你的名字和邮箱
- `project.urls` - GitHub 仓库链接
- `readme` - 指向 README.md
- `classifiers` - 正确的分类标签

### 3. 创建 LICENSE 文件

如果选择 MIT 许可证，创建 `LICENSE` 文件。

### 4. 首次上传

第一次上传可能需要额外验证邮箱。
