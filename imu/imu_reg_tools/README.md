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
./imu_diag [spi_dev] [sample_type] [hz]        全链路诊断 + 实时监控
./imu_diag <spi_dev> range show                查看当前量程
./imu_diag <spi_dev> range accel <range_g>     修改加速度计量程
./imu_diag <spi_dev> range gyro <range_dps>    修改陀螺仪量程
./imu_diag <spi_dev> restore                   恢复机器人默认配置
```

> **写寄存器前必须停止 `imu_node` / `lowlevel_service` 等正在访问同一
> SPI 设备的服务。** 工具修改的是芯片易失寄存器，IMU 驱动重启后会重新写入
> 生产默认配置。

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

# 查看当前量程及寄存器值
./imu_diag /dev/spidev0.0 range show

# 加速度计支持 ±2g、±4g、±8g、±16g
./imu_diag /dev/spidev0.0 range accel 8

# 陀螺仪支持 ±125/250/500/1000/2000/4000 dps
./imu_diag /dev/spidev0.0 range gyro 1000

# 软件复位后恢复机器人生产默认值：
# Accel 104Hz ±4g，Gyro 104Hz ±250dps，BDU=1，IF_INC=1
./imu_diag /dev/spidev0.0 restore
```

量程命令采用 read-modify-write，只修改量程位，保留当前 ODR 和滤波配置；
写入后会强制回读校验。诊断和监控模式会根据当前量程自动选择正确的
mg/LSB、mdps/LSB 换算系数。

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

### 故障 3：WHO_AM_I 正常，但 `restore` 写后回读不一致
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

工具根据 CTRL1_XL/CTRL2_G 当前量程动态选择换算系数：

- Accel ±2/4/8/16g：0.061/0.122/0.244/0.488 mg/LSB
- Gyro ±125/250/500/1000/2000/4000dps：
  4.37/8.75/17.5/35/70/140 mdps/LSB
- Temp：`raw / 256 + 25` → 单位 °C

机器人驱动 `imu.cpp` 仍固定按 ±4g、±250dps 换算；驱动启动时也会恢复该
量程。因此本工具的量程修改用于停止驱动后的独立诊断和实验。
