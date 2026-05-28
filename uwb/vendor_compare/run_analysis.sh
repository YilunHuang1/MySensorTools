#!/bin/bash
# UWB数据分析系统启动脚本

echo "🎯 启动UWB数据专业分析系统..."
echo "================================================"

# 检查Python3是否可用
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到python3，请先安装Python 3.x"
    exit 1
fi

# 检查必要的Python包
echo "📦 检查依赖包..."
python3 -c "import pandas, numpy, matplotlib, seaborn, scipy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少必要的Python包，正在安装..."
    pip3 install pandas numpy matplotlib seaborn scipy
    if [ $? -ne 0 ]; then
        echo "❌ 依赖包安装失败，请手动安装: pip3 install pandas numpy matplotlib seaborn scipy"
        exit 1
    fi
fi

echo "✅ 依赖检查完成"
echo "🚀 开始分析..."
echo "================================================"

# 运行分析程序
python3 main_analysis.py "$@"

echo "================================================"
echo "✅ 分析完成！查看 analysis_results/ 目录获取结果"