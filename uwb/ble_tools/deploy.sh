#!/bin/bash
# ─────────────────────────────────────────────────────────
# deploy.sh - 一键部署 UWB BLE 脚本到机器狗
# Usage: bash deploy.sh
# ─────────────────────────────────────────────────────────

set -e

DOG_HOST="root@home-x5"
REMOTE_DIR="/app/uwb_iphone"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 需要部署的文件
FILES=(
    "run_uwb_ble.py"
    "SerialHandlerStandalone.py"
    "CmdBuilder.py"
    "PacketParser.py"
    "crc16_utils.py"
    "start_uwb.sh"
)

echo "============================================"
echo "  UWB BLE 部署脚本"
echo "============================================"
echo "  目标主机: ${DOG_HOST}"
echo "  目标目录: ${REMOTE_DIR}"
echo "============================================"

# Step 0: 重新挂载 /app 为可写
echo ""
echo "🔧 Step 0: 重新挂载 /app 为可写模式..."
ssh ${DOG_HOST} "mount -o remount,rw /app || echo '⚠️ remount 失败，可能已经是可写模式'"

# Step 1: 在狗子上创建目标目录并设置权限
echo ""
echo "📁 Step 1: 创建远程目录 ${REMOTE_DIR} ..."
ssh ${DOG_HOST} "mkdir -p ${REMOTE_DIR} && chmod 777 ${REMOTE_DIR}"

# Step 2: 拷贝文件
echo "📦 Step 2: 拷贝文件到狗子..."
for f in "${FILES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        echo "   ├── ${f}"
        scp "${SCRIPT_DIR}/${f}" "${DOG_HOST}:${REMOTE_DIR}/${f}" || {
            echo "   ├── ⚠️  ${f} 拷贝失败，尝试使用临时目录..."
            scp "${SCRIPT_DIR}/${f}" "${DOG_HOST}:/tmp/${f}"
            ssh ${DOG_HOST} "mv /tmp/${f} ${REMOTE_DIR}/${f}"
        }
    else
        echo "   ├── ⚠️  ${f} 不存在，跳过"
    fi
done
echo "   └── ✅ 文件拷贝完成"

# Step 3: 检测依赖
echo ""
echo "🔍 Step 3: 检测狗子上的环境..."
ssh ${DOG_HOST} bash <<'REMOTE_SCRIPT'
echo "--- Python3 ---"
python3 --version 2>/dev/null || echo "❌ python3 未安装"

echo ""
echo "--- 检测 pyserial ---"
python3 -c "import serial; print('✅ pyserial OK')" 2>/dev/null || {
    echo "⚠️ pyserial 未安装，正在安装..."
    pip3 install pyserial 2>/dev/null || python3 -m pip install pyserial
}

echo ""
echo "--- 检测 dbus-python ---"
python3 -c "import dbus; print('✅ dbus-python OK')" 2>/dev/null || {
    echo "⚠️ dbus-python 未安装"
    echo "   尝试: sudo apt install -y python3-dbus"
}

echo ""
echo "--- 检测 PyGObject ---"
python3 -c "from gi.repository import GLib; print('✅ PyGObject OK')" 2>/dev/null || {
    echo "⚠️ PyGObject 未安装"
    echo "   尝试: sudo apt install -y python3-gi"
}

echo ""
echo "--- 检测串口 ---"
for port in /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyS7; do
    if [ -e "$port" ]; then
        echo "✅ 找到串口: $port"
    fi
done

echo ""
echo "--- 检测蓝牙 ---"
systemctl is-active bluetooth >/dev/null 2>&1 && echo "✅ bluetooth 服务运行中" || echo "⚠️ bluetooth 服务未运行"
hciconfig hci0 2>/dev/null | head -3 || echo "⚠️ 没有找到 hci0 蓝牙适配器"
REMOTE_SCRIPT

echo ""
echo "============================================"
echo "✅ 部署完成！"
echo ""
echo "接下来请 SSH 到狗子上运行："
echo ""
echo "  ssh ${DOG_HOST}"
echo "  cd ${REMOTE_DIR}"
echo "  bash start_uwb.sh          # 使用默认串口 /dev/ttyUSB0"
echo "  # 或指定串口："
echo "  # bash start_uwb.sh /dev/ttyS7"
echo ""
echo "手动运行（如需调试）："
echo "  python3 run_uwb_ble.py --port /dev/ttyUSB0"
echo "============================================"
