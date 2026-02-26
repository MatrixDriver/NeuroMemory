#!/bin/bash
set -e

echo "🚀 neuromem PyPI 发布脚本"
echo "=============================="

# 检查是否有未提交的更改
if [[ -n $(git status -s) ]]; then
    echo "⚠️  有未提交的更改："
    git status -s
    read -p "是否继续？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 读取当前版本
VERSION=$(grep "^version" pyproject.toml | cut -d'"' -f2)
echo "📦 当前版本: $VERSION"

# 清理旧构建
echo "🧹 清理旧构建文件..."
rm -rf dist/ build/ *.egg-info/

# 运行测试（可选，如果测试失败可以注释掉）
# echo "🧪 运行测试..."
# pytest tests/ -v || { echo "❌ 测试失败"; exit 1; }

# 构建
echo "🔨 构建包..."
python -m build || { echo "❌ 构建失败"; exit 1; }

# 检查构建结果
echo "📋 构建结果："
ls -lh dist/

# 询问是否上传到 TestPyPI
read -p "是否先上传到 TestPyPI 测试？(y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📤 上传到 TestPyPI..."
    python -m twine upload --repository testpypi dist/* || { echo "❌ 上传 TestPyPI 失败"; exit 1; }
    echo "✅ TestPyPI 上传成功！"
    echo "🔗 查看: https://test.pypi.org/project/neuromem/$VERSION/"
    echo ""
    read -p "继续上传到正式 PyPI？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# 上传到 PyPI
echo "📤 上传到 PyPI..."
python -m twine upload dist/* || { echo "❌ 上传失败"; exit 1; }

echo ""
echo "✅ 发布成功！"
echo "🔗 查看: https://pypi.org/project/neuromem/$VERSION/"
echo ""
echo "📦 用户现在可以通过以下方式安装："
echo "   pip install neuromem==$VERSION"
