#!/bin/bash
# 快速启动 UWB BLE 测距程序
# Usage: bash start_uwb.sh [port]

PORT=${1:-/dev/ttyUSB0}

echo "🛑 停止旧进程..."
killall python3 2>/dev/null
sleep 1

echo "🔄 重启蓝牙服务..."
systemctl restart bluetooth
sleep 2

echo "✅ 启动蓝牙适配器..."
hciconfig hci0 up

echo ""
echo "🚀 启动 UWB BLE 测距程序..."
echo "   串口: ${PORT}"
echo "   按 Ctrl+C 停止"
echo ""

cd /app/uwb_iphone
python3 run_uwb_ble.py --port ${PORT}
