# IMU 诊断工具 — imu_diag

ASM330LHHTR IMU 全链路诊断工具，用于快速定位 IMU 数据异常（全 0 / 偶发丢失）的根因。

> 源码同步备份自：`vita-robot/src/middleware/sensor/imu/test/imu_diag.cpp`  
> 放在此处是为了防止 vita-robot 代码更新覆盖丢失。

---

## 编译

在机器人（S100/X5，aarch64 Linux）上直接编译，**无任何外部依赖**：

```bash
g++ -std=c++17 -O2 imu_diag.cpp -o imu_diag
```

---

## 用法

```
./imu_diag [spi_dev] [sample_type] [hz]   全链路诊断 + 实时监控
./imu_diag [spi_dev] init                  手动写入 CTRL 寄存器使 IMU 上电
./imu_diag [spi_dev] write <addr> <val>    写单个寄存器 (hex)
./imu_diag [spi_dev] read  <addr>          读单个寄存器 (hex)
```

| 平台 | SPI 设备 | sample_type |
|------|----------|-------------|
| S100 | `/dev/spidev0.0` | `bsample` |
| X5   | `/dev/spidev2.0` | `bsample` |

### 常用示例

```bash
# 全链路诊断 + 实时监控（最常用）
./imu_diag /dev/spidev0.0 bsample

# 指定监控频率 50Hz
./imu_diag /dev/spidev0.0 bsample 50

# 手动 Init（IMU 处于 Power-Down 时使用）
./imu_diag /dev/spidev0.0 init

# 读单个寄存器
./imu_diag /dev/spidev0.0 read 0x0F     # WHO_AM_I

# 写单个寄存器
./imu_diag /dev/spidev0.0 write 0x10 0x48   # CTRL1_XL: 104Hz ±4g
```

---

## 诊断输出说明

工具按如下 6 层逐层排查，自动定位根因：

| 层级 | 检查内容 | 能排除什么 |
|------|----------|------------|
| **Layer 1** | `WHO_AM_I` 是否 = `0x6B` | SPI 线路 / CS 极性 / 供电 |
| **Layer 2** | `CTRL1~CTRL3` 寄存器值 | `Init()` 未执行 / SPI Write 失败 |
| **Layer 3** | `STATUS_REG` `XLDA`/`GDA` bit | ODR=0 Power-Down / BDU 锁定 |
| **Layer 4** | 输出寄存器原始 hex + int16 | **寄存器本身是否就是 0** |
| **Layer 5** | 换算后物理量 + accel norm | scale 系数是否正确 |
| **Layer 6** | 坐标变换后结果 | bsample/asample 变换是否异常 |
| **Monitor** | 实时滚动输出，全 0 行红色高亮 | 偶发 vs 持续问题 |

---

## 常见故障与根因

### 故障 1：WHO_AM_I 读回 `0x00`
- MISO 被拉低，可能原因：芯片供电异常 / 芯片损坏 / MISO 短路到 GND

### 故障 2：WHO_AM_I 读回 `0xFF`
- MISO 悬空，SPI 线未接 / CS 极性错误

### 故障 3：WHO_AM_I 正常，CTRL 寄存器全 0，写操作 readback 全 0
```
Writing 0x48 to register 0x10 ...
  ✗ MISMATCH: wrote 0x48, read back 0x00
```
- **MOSI（SDI）线路故障**（虚焊 / 断路）
- 读走 MISO，写走 MOSI，两者独立
- 虚焊时 WHO_AM_I 偶尔能读到（1 字节概率性成功），写操作需 2 字节全部到达故障率更高
- **修复：补焊 IMU 的 MOSI/SDI 引脚**

### 故障 4：WHO_AM_I 正常，CTRL 正常，数据全 0
- BDU=1 时数据寄存器被锁定，尝试重新读取
- ODR 太低，等待 DATA READY bit 置位

### 故障 5：寄存器有数据，但 ROS topic 全 0
- 检查 `imu_test.cpp` 中消息赋值字段名是否与订阅端匹配
- 使用 `ros2 topic echo /imu_raw` 确认发布端是否有数据

---

## 关键寄存器速查

| 寄存器 | 地址 | 正常值 | 说明 |
|--------|------|--------|------|
| WHO_AM_I | 0x0F | 0x6B | 芯片 ID，只读 |
| CTRL1_XL | 0x10 | 0x48 | Accel 104Hz ±4g |
| CTRL2_G  | 0x11 | 0x40 | Gyro  104Hz ±250dps |
| CTRL3_C  | 0x12 | 0x44 | BDU=1, IF_INC=1 |
| STATUS_REG | 0x1E | 0x03 | bit0=XLDA, bit1=GDA |
| OUTX_L_G | 0x22 | — | Gyro X 低字节 |
| OUTX_L_XL | 0x28 | — | Accel X 低字节 |

换算系数（与 `imu.cpp` 一致）：
- Accel: `raw × 0.122 / 1000` → 单位 g（±4g 量程）
- Gyro:  `raw × 8.75 / 1000`  → 单位 deg/s（±250dps 量程）
- Temp:  `raw / 256 + 25`     → 单位 °C
