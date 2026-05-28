#!/bin/bash

# UWB数据处理工具包安装脚本

echo "UWB数据处理工具包安装脚本"
echo "=========================="

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "错误: 需要Python 3.8或更高版本，当前版本: $python_version"
    exit 1
fi

echo "Python版本检查通过: $python_version"

# 创建虚拟环境（可选）
read -p "是否创建虚拟环境? (y/n): " create_venv
if [ "$create_venv" = "y" ]; then
    venv_name="uwb_toolkit_env"
    echo "创建虚拟环境: $venv_name"
    python3 -m venv $venv_name
    source $venv_name/bin/activate
    echo "虚拟环境已激活"
fi

# 安装依赖
echo "安装依赖包..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "依赖安装成功!"
else
    echo "错误: 依赖安装失败"
    exit 1
fi

# 创建符号链接（可选）
read -p "是否创建命令行工具的符号链接? (y/n): " create_link
if [ "$create_link" = "y" ]; then
    script_dir=$(pwd)
    link_name="uwb_toolkit"
    
    if [ -L "/usr/local/bin/$link_name" ]; then
        echo "符号链接已存在，正在删除..."
        sudo rm /usr/local/bin/$link_name
    fi
    
    echo "创建符号链接: /usr/local/bin/$link_name -> $script_dir/uwb_toolkit_cli.py"
    sudo ln -s "$script_dir/uwb_toolkit_cli.py" "/usr/local/bin/$link_name"
    sudo chmod +x "/usr/local/bin/$link_name"
    echo "符号链接创建成功，现在可以使用 'uwb_toolkit' 命令"
fi

echo ""
echo "安装完成!"
echo "使用方法:"
echo "  python uwb_toolkit_cli.py --help"
if [ "$create_link" = "y" ]; then
    echo "  uwb_toolkit --help"
fi
echo ""
echo "更多使用方法请参考 README.md"