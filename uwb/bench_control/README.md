# X5 UWB 台架控制工具

`uwb_bench.sh` 直接运行在 X5，不依赖 Mac 端 Python，也不使用 SSH
编排 X5/S100。

脚本通过 X5 本机 ROS2 接口完成：

- `/uwb/pair_tag`：设置 Tag 名称
- `/function/context/set_context`：启停 UWB 测距
- `/execute_s100_command`：临时停止或恢复 S100 的 `vln.service`
- `/uwb/state`、`/uwb/data`：检查状态和测距数据
- 必要时在 X5 本机重启 Bluetooth、BLE 和 UWB 服务

## 部署

在开发机执行：

```bash
scp uwb_bench.sh home-x5:/app/uwb/uwb_bench.sh
ssh home-x5 'chmod +x /app/uwb/uwb_bench.sh'
```

也可以手工把文件复制到 `/app/uwb/uwb_bench.sh` 后执行
`chmod +x`。

## 使用

登录 X5：

```bash
ssh home-x5
cd /app/uwb
```

使用脚本内的默认 Tag 开始测距：

```bash
./uwb_bench.sh start
```

临时指定其他 Tag，不需要修改文件：

```bash
./uwb_bench.sh start Vbot_F274C9EC1DB0
```

查看状态和一帧数据：

```bash
./uwb_bench.sh status
```

停止测距并恢复 S100 VLN：

```bash
./uwb_bench.sh stop
```

## 修改默认 Tag

编辑脚本开头：

```bash
DEFAULT_TAG_NAME="Vbot_F274C9EC1DB0"
```

Tag 名字中的十六进制部分对应 BLE MAC：
`F274C9EC1DB0` 对应 `F2:74:C9:EC:1D:B0`。

## 行为说明

`start` 成功后，`vln.service` 会保持停止，避免它把
`FOLLOW_STATUS` 重置为 `STOP`。完成台架测试后应执行 `stop`，
它会停止测距并恢复 `vln.service`。

如果 `start` 中途失败，脚本会尽力停止测距并恢复 VLN。
BLE 无法进入 `CONNECTED` 时，脚本只自动重启一次 X5 的
`bluetooth.service`、`ble.service` 和 `uwb.service`。

Tag 应放在 X5 蓝牙天线附近。RSSI 长期低于约 `-90 dBm` 时，
GATT 解析和 Notify 获取可能失败，脚本重启服务也无法解决射频链路问题。
