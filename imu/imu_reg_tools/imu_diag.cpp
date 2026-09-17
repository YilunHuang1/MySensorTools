/**
 * imu_diag.cpp — ASM330LHHTR IMU 全链路诊断工具
 *
 * 用途：快速定位 IMU 数据全 0 的根因，逐层排查：
 *   [Layer 1] SPI 通信   — WHO_AM_I 是否正确
 *   [Layer 2] 寄存器配置 — CTRL1~CTRL3 是否写入
 *   [Layer 3] DATA READY — STATUS_REG XLDA/GDA bit
 *   [Layer 4] 原始寄存器 — 读回 hex 字节，看寄存器本身是否全 0
 *   [Layer 5] 换算值     — int16 → float，验证 scale 是否正常
 *   [Layer 6] 坐标变换   — 应用 bsample/asample 变换后结果
 *
 * 编译（在机器人上）:
 *   g++ -std=c++14 -O2 imu_diag.cpp -o imu_diag
 *
 * 用法:
 *   ./imu_diag                    # 默认 spidev0.0，运行诊断 + 实时监控
 *   ./imu_diag /dev/spidev2.0     # 指定 SPI 设备 (X5 平台)
 *   ./imu_diag /dev/spidev2.0 bsample   # 指定坐标系类型
 *   ./imu_diag /dev/spidev0.0 range accel 8
 *   ./imu_diag /dev/spidev0.0 range gyro 1000
 *   ./imu_diag /dev/spidev0.0 restore
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <cmath>
#include <string>

// ============================================================
// SPI 配置
// ============================================================
static const uint8_t  kSpiMode  = SPI_MODE_3;
static const uint8_t  kSpiBits  = 8;
static const uint32_t kSpiSpeed = 1000000;  // 1 MHz

// ============================================================
// ASM330 寄存器地址
// ============================================================
#define REG_WHO_AM_I   0x0F
#define REG_CTRL1_XL   0x10
#define REG_CTRL2_G    0x11
#define REG_CTRL3_C    0x12
#define REG_CTRL4_C    0x13
#define REG_CTRL5_C    0x14
#define REG_CTRL6_C    0x15
#define REG_CTRL7_G    0x16
#define REG_CTRL8_XL   0x17
#define REG_STATUS_REG 0x1E
#define REG_OUT_TEMP_L 0x20
#define REG_OUT_TEMP_H 0x21
#define REG_OUTX_L_G   0x22
#define REG_OUTX_H_G   0x23
#define REG_OUTY_L_G   0x24
#define REG_OUTY_H_G   0x25
#define REG_OUTZ_L_G   0x26
#define REG_OUTZ_H_G   0x27
#define REG_OUTX_L_XL  0x28
#define REG_OUTX_H_XL  0x29
#define REG_OUTY_L_XL  0x2A
#define REG_OUTY_H_XL  0x2B
#define REG_OUTZ_L_XL  0x2C
#define REG_OUTZ_H_XL  0x2D

static constexpr float kTempScale  = 256.0f;
static constexpr float kTempOffset = 25.0f;

static volatile bool g_running = true;

// ============================================================
// ANSI 颜色
// ============================================================
#define COLOR_RED    "\033[31m"
#define COLOR_GREEN  "\033[32m"
#define COLOR_YELLOW "\033[33m"
#define COLOR_CYAN   "\033[36m"
#define COLOR_RESET  "\033[0m"
#define COLOR_BOLD   "\033[1m"

static void sig_handler(int) { g_running = false; }

// ============================================================
// SPI 操作
// ============================================================
static int spi_fd = -1;

static bool spi_open(const char* dev) {
    spi_fd = open(dev, O_RDWR);
    if (spi_fd < 0) {
        fprintf(stderr, COLOR_RED "Error: Cannot open %s: %s\n" COLOR_RESET,
                dev, strerror(errno));
        return false;
    }
    if (ioctl(spi_fd, SPI_IOC_WR_MODE, &kSpiMode) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &kSpiBits) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &kSpiSpeed) < 0) {
        fprintf(stderr, COLOR_RED "Error: SPI ioctl setup failed\n" COLOR_RESET);
        close(spi_fd);
        return false;
    }
    return true;
}

static uint8_t reg_read(uint8_t reg) {
    uint8_t tx[2] = {(uint8_t)(reg | 0x80), 0x00};
    uint8_t rx[2] = {0x00, 0x00};
    struct spi_ioc_transfer tr;
    memset(&tr, 0, sizeof(tr));
    tr.tx_buf        = (unsigned long)tx;
    tr.rx_buf        = (unsigned long)rx;
    tr.len           = 2;
    tr.speed_hz      = kSpiSpeed;
    tr.bits_per_word = kSpiBits;
    if (ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr) < 0) {
        fprintf(stderr, COLOR_RED "SPI transfer error for reg 0x%02X\n" COLOR_RESET, reg);
        return 0xFF;
    }
    return rx[1];
}

static bool reg_write(uint8_t reg, uint8_t val) {
    uint8_t tx[2] = {(uint8_t)(reg & 0x7F), val};
    uint8_t rx[2] = {0};
    struct spi_ioc_transfer tr;
    memset(&tr, 0, sizeof(tr));
    tr.tx_buf        = (unsigned long)tx;
    tr.rx_buf        = (unsigned long)rx;
    tr.len           = 2;
    tr.speed_hz      = kSpiSpeed;
    tr.bits_per_word = kSpiBits;
    if (ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr) < 0) {
        fprintf(stderr, COLOR_RED "SPI write error for reg 0x%02X: %s\n" COLOR_RESET,
                reg, strerror(errno));
        return false;
    }
    return true;
}

static bool reg_write_verify(uint8_t reg, uint8_t val, uint8_t mask = 0xFF) {
    if (!reg_write(reg, val)) return false;
    uint8_t readback = reg_read(reg);
    if (((readback ^ val) & mask) != 0) {
        fprintf(stderr, COLOR_RED
                "Write verify failed: reg 0x%02X, wrote 0x%02X, read 0x%02X\n"
                COLOR_RESET, reg, val, readback);
        return false;
    }
    return true;
}

// ============================================================
// 量程解码与换算系数
// ============================================================
static int accel_range_from_ctrl(uint8_t ctrl) {
    switch ((ctrl >> 2) & 0x03) {
        case 0: return 2;
        case 1: return 16;
        case 2: return 4;
        case 3: return 8;
    }
    return 0;
}

static float accel_scale_from_ctrl(uint8_t ctrl) {
    switch (accel_range_from_ctrl(ctrl)) {
        case 2:  return 0.061f;
        case 4:  return 0.122f;
        case 8:  return 0.244f;
        case 16: return 0.488f;
    }
    return 0.0f;
}

static int gyro_range_from_ctrl(uint8_t ctrl) {
    if (ctrl & 0x01) return 4000;
    if (ctrl & 0x02) return 125;
    switch ((ctrl >> 2) & 0x03) {
        case 0: return 250;
        case 1: return 500;
        case 2: return 1000;
        case 3: return 2000;
    }
    return 0;
}

static float gyro_scale_from_ctrl(uint8_t ctrl) {
    switch (gyro_range_from_ctrl(ctrl)) {
        case 125:  return 4.37f;
        case 250:  return 8.75f;
        case 500:  return 17.5f;
        case 1000: return 35.0f;
        case 2000: return 70.0f;
        case 4000: return 140.0f;
    }
    return 0.0f;
}

static bool parse_int(const char* text, int& value) {
    errno = 0;
    char* end = nullptr;
    long parsed = strtol(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0' ||
        parsed < 0 || parsed > 1000000) {
        return false;
    }
    value = static_cast<int>(parsed);
    return true;
}

static void print_range_config() {
    uint8_t ctrl1 = reg_read(REG_CTRL1_XL);
    uint8_t ctrl2 = reg_read(REG_CTRL2_G);
    printf("  Accelerometer: ±%dg, CTRL1_XL=0x%02X, %.3f mg/LSB\n",
           accel_range_from_ctrl(ctrl1), ctrl1, accel_scale_from_ctrl(ctrl1));
    printf("  Gyroscope:     ±%d dps, CTRL2_G=0x%02X, %.2f mdps/LSB\n",
           gyro_range_from_ctrl(ctrl2), ctrl2, gyro_scale_from_ctrl(ctrl2));
}

static bool set_accel_range(int range_g) {
    uint8_t fs_bits = 0;
    switch (range_g) {
        case 2:  fs_bits = 0x00; break;
        case 4:  fs_bits = 0x08; break;
        case 8:  fs_bits = 0x0C; break;
        case 16: fs_bits = 0x04; break;
        default:
            fprintf(stderr, "Invalid accel range: %d (allowed: 2, 4, 8, 16)\n",
                    range_g);
            return false;
    }

    uint8_t old_value = reg_read(REG_CTRL1_XL);
    uint8_t odr = (old_value >> 4) & 0x0F;
    if (odr > 0x0A || (old_value & 0x01) != 0) {
        fprintf(stderr, COLOR_RED
                "CTRL1_XL readback is invalid (0x%02X); refusing to write\n"
                COLOR_RESET, old_value);
        return false;
    }
    uint8_t new_value = (uint8_t)((old_value & ~0x0C) | fs_bits);
    printf("  CTRL1_XL: 0x%02X -> 0x%02X  (±%dg)\n",
           old_value, new_value, range_g);
    if (!reg_write_verify(REG_CTRL1_XL, new_value)) return false;
    printf(COLOR_GREEN "  Range updated and verified.\n" COLOR_RESET);
    return true;
}

static bool set_gyro_range(int range_dps) {
    uint8_t fs_bits = 0;
    switch (range_dps) {
        case 125:  fs_bits = 0x02; break;
        case 250:  fs_bits = 0x00; break;
        case 500:  fs_bits = 0x04; break;
        case 1000: fs_bits = 0x08; break;
        case 2000: fs_bits = 0x0C; break;
        case 4000: fs_bits = 0x01; break;
        default:
            fprintf(stderr,
                    "Invalid gyro range: %d (allowed: 125, 250, 500, 1000, 2000, 4000)\n",
                    range_dps);
            return false;
    }

    uint8_t old_value = reg_read(REG_CTRL2_G);
    uint8_t odr = (old_value >> 4) & 0x0F;
    if (odr > 0x0A) {
        fprintf(stderr, COLOR_RED
                "CTRL2_G readback is invalid (0x%02X); refusing to write\n"
                COLOR_RESET, old_value);
        return false;
    }
    // 低 4 位全部规范化，避免 FS_G、FS_125、FS_4000 产生冲突组合。
    uint8_t new_value = (uint8_t)((old_value & 0xF0) | fs_bits);
    printf("  CTRL2_G: 0x%02X -> 0x%02X  (±%d dps)\n",
           old_value, new_value, range_dps);
    if (!reg_write_verify(REG_CTRL2_G, new_value)) return false;
    printf(COLOR_GREEN "  Range updated and verified.\n" COLOR_RESET);
    return true;
}

static bool restore_default_config() {
    printf("  Restoring robot production defaults: 104Hz, ±4g, ±250dps...\n");

    if (!reg_write(REG_CTRL3_C, 0x01)) return false;
    bool reset_done = false;
    for (int i = 0; i < 100; ++i) {
        usleep(1000);
        if ((reg_read(REG_CTRL3_C) & 0x01) == 0) {
            reset_done = true;
            break;
        }
    }
    if (!reset_done) {
        fprintf(stderr, COLOR_RED "Software reset did not complete\n" COLOR_RESET);
        return false;
    }

    usleep(100000);
    if (!reg_write_verify(REG_CTRL1_XL, 0x48) ||
        !reg_write_verify(REG_CTRL2_G, 0x40) ||
        !reg_write_verify(REG_CTRL3_C, 0x44)) {
        return false;
    }
    usleep(100000);
    printf(COLOR_GREEN "  Default configuration restored and verified.\n" COLOR_RESET);
    print_range_config();
    return true;
}

// ============================================================
// 读 6 轴原始字节（连续读，减少 SPI 时延）
// ============================================================
static void read_raw_xyz(uint8_t base_reg, int16_t& rx, int16_t& ry, int16_t& rz) {
    uint8_t xl = reg_read(base_reg + 0);
    uint8_t xh = reg_read(base_reg + 1);
    uint8_t yl = reg_read(base_reg + 2);
    uint8_t yh = reg_read(base_reg + 3);
    uint8_t zl = reg_read(base_reg + 4);
    uint8_t zh = reg_read(base_reg + 5);
    rx = (int16_t)((xh << 8) | xl);
    ry = (int16_t)((yh << 8) | yl);
    rz = (int16_t)((zh << 8) | zl);
}

// ============================================================
// 坐标变换（与 imu.cpp 完全一致）
// ============================================================
static void coord_transform_accel(const std::string& type,
                                   float& ax, float& ay, float& az) {
    if (type == "bsample") {
        float tmp = ax;
        ax = ay;
        ay = -tmp;
    } else {
        ay = -ay;
        az = -az;
    }
}

static void coord_transform_gyro(const std::string& type,
                                  float& gx, float& gy, float& gz) {
    if (type == "bsample") {
        float tmp = gx;
        gx = gy;
        gy = -tmp;
    } else {
        gy = -gy;
        gz = -gz;
    }
}

// ============================================================
// 辅助：打印 PASS/FAIL
// ============================================================
static void print_check(const char* name, bool ok, const char* detail = nullptr) {
    printf("  [%s] %s", ok ? COLOR_GREEN "PASS" COLOR_RESET
                            : COLOR_RED   "FAIL" COLOR_RESET, name);
    if (detail) printf("  →  %s", detail);
    printf("\n");
}

// ============================================================
// Layer 1: SPI + WHO_AM_I
// ============================================================
static bool check_who_am_i() {
    printf(COLOR_BOLD "\n[Layer 1] SPI 通信 / WHO_AM_I\n" COLOR_RESET);
    uint8_t id = reg_read(REG_WHO_AM_I);
    char detail[64];
    snprintf(detail, sizeof(detail), "读回 0x%02X (期望 0x6B)", id);
    bool ok = (id == 0x6B);
    print_check("WHO_AM_I == 0x6B", ok, detail);
    if (!ok) {
        if (id == 0xFF)
            printf(COLOR_YELLOW "    提示: 读回 0xFF，可能 SPI MISO 线未接 或 CS 极性错误\n" COLOR_RESET);
        else if (id == 0x00)
            printf(COLOR_YELLOW "    提示: 读回 0x00，可能 MISO 拉低 或 供电问题\n" COLOR_RESET);
    }
    return ok;
}

// ============================================================
// Layer 2: 寄存器配置
// ============================================================
static void check_ctrl_regs() {
    printf(COLOR_BOLD "\n[Layer 2] CTRL 寄存器配置\n" COLOR_RESET);

    uint8_t ctrl1 = reg_read(REG_CTRL1_XL);
    uint8_t ctrl2 = reg_read(REG_CTRL2_G);
    uint8_t ctrl3 = reg_read(REG_CTRL3_C);
    char detail[160];

    uint8_t accel_odr = (ctrl1 >> 4) & 0x0F;
    bool accel_ok = accel_odr > 0 && accel_odr <= 0x0A &&
                    (ctrl1 & 0x01) == 0;
    snprintf(detail, sizeof(detail), "0x%02X  ODR code=0x%X, ±%dg, %.3f mg/LSB",
             ctrl1, (ctrl1 >> 4) & 0x0F, accel_range_from_ctrl(ctrl1),
             accel_scale_from_ctrl(ctrl1));
    print_check("CTRL1_XL (0x10)", accel_ok, detail);

    uint8_t gyro_odr = (ctrl2 >> 4) & 0x0F;
    bool gyro_ok = gyro_odr > 0 && gyro_odr <= 0x0A &&
                   !((ctrl2 & 0x01) && (ctrl2 & 0x0E));
    snprintf(detail, sizeof(detail), "0x%02X  ODR code=0x%X, ±%d dps, %.2f mdps/LSB",
             ctrl2, (ctrl2 >> 4) & 0x0F, gyro_range_from_ctrl(ctrl2),
             gyro_scale_from_ctrl(ctrl2));
    print_check("CTRL2_G  (0x11)", gyro_ok, detail);

    snprintf(detail, sizeof(detail), "0x%02X  BDU=%d, IF_INC=%d",
             ctrl3, (ctrl3 >> 6) & 1, (ctrl3 >> 2) & 1);
    print_check("CTRL3_C  (0x12)", (ctrl3 & 0x44) == 0x44, detail);

    if (ctrl1 == 0x00 || ctrl2 == 0x00)
        printf(COLOR_YELLOW "    提示: ODR 为 Power-down，请执行 restore 恢复默认配置\n" COLOR_RESET);

    // 打印其余 CTRL 供参考
    printf("  ---- 其余 CTRL (仅供参考) ----\n");
    uint8_t addrs[] = {REG_CTRL4_C, REG_CTRL5_C, REG_CTRL6_C,
                       REG_CTRL7_G, REG_CTRL8_XL};
    const char* names[] = {"CTRL4_C (0x13)", "CTRL5_C (0x14)",
                            "CTRL6_C (0x15)", "CTRL7_G (0x16)",
                            "CTRL8_XL(0x17)"};
    for (int i = 0; i < 5; i++)
        printf("    %s = 0x%02X\n", names[i], reg_read(addrs[i]));
}

// ============================================================
// Layer 3: STATUS_REG — 数据就绪
// ============================================================
static void check_status_reg() {
    printf(COLOR_BOLD "\n[Layer 3] STATUS_REG (0x1E) 数据就绪位\n" COLOR_RESET);
    // 等最多 100ms，每 5ms 采样一次
    uint8_t status = 0;
    for (int i = 0; i < 20; i++) {
        status = reg_read(REG_STATUS_REG);
        if ((status & 0x03) == 0x03) break;
        usleep(5000);
    }
    char detail[64];
    snprintf(detail, sizeof(detail), "STATUS_REG = 0x%02X", status);
    bool xlda = (status & 0x01) != 0;
    bool gda  = (status & 0x02) != 0;
    print_check("XLDA (accel data ready)", xlda, xlda ? "bit 0 = 1" : "bit 0 = 0 ← 加速度数据未就绪!");
    print_check("GDA  (gyro  data ready)", gda,  gda  ? "bit 1 = 1" : "bit 1 = 0 ← 陀螺仪数据未就绪!");
    if (!xlda || !gda)
        printf(COLOR_YELLOW "    提示: 若 ODR 配置正确但 bit 未置位，可能 BDU 未使能 或 ODR 为 0\n" COLOR_RESET);
}

// ============================================================
// Layer 4 + 5 + 6: 原始字节 → int16 → float → 坐标变换
// ============================================================
static void check_one_sample(const std::string& sample_type) {
    printf(COLOR_BOLD "\n[Layer 4-6] 原始寄存器 → 换算 → 坐标变换 (sample_type=%s)\n" COLOR_RESET,
           sample_type.c_str());

    int16_t rx_g, ry_g, rz_g;
    int16_t rx_a, ry_a, rz_a;

    read_raw_xyz(REG_OUTX_L_G,  rx_g, ry_g, rz_g);
    read_raw_xyz(REG_OUTX_L_XL, rx_a, ry_a, rz_a);
    uint8_t tl = reg_read(REG_OUT_TEMP_L);
    uint8_t th = reg_read(REG_OUT_TEMP_H);
    int16_t raw_temp = (int16_t)((th << 8) | tl);

    // Layer 4: 原始 hex
    printf("\n  [Layer 4] 寄存器原始字节\n");
    printf("    Gyro  OUTX_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(rx_g & 0xFF), (uint8_t)((rx_g >> 8) & 0xFF), rx_g);
    printf("    Gyro  OUTY_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(ry_g & 0xFF), (uint8_t)((ry_g >> 8) & 0xFF), ry_g);
    printf("    Gyro  OUTZ_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(rz_g & 0xFF), (uint8_t)((rz_g >> 8) & 0xFF), rz_g);
    printf("    Accel OUTX_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(rx_a & 0xFF), (uint8_t)((rx_a >> 8) & 0xFF), rx_a);
    printf("    Accel OUTY_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(ry_a & 0xFF), (uint8_t)((ry_a >> 8) & 0xFF), ry_a);
    printf("    Accel OUTZ_L/H = 0x%02X 0x%02X  →  int16 = %6d\n",
           (uint8_t)(rz_a & 0xFF), (uint8_t)((rz_a >> 8) & 0xFF), rz_a);
    printf("    Temp  OUT_L/H  = 0x%02X 0x%02X  →  int16 = %6d\n",
           tl, th, raw_temp);

    bool raw_zero = (rx_g == 0 && ry_g == 0 && rz_g == 0 &&
                     rx_a == 0 && ry_a == 0 && rz_a == 0);
    bool raw_stuck = (rx_g == (int16_t)0xFFFF && ry_g == (int16_t)0xFFFF);

    if (raw_zero)
        printf(COLOR_RED "    ⚠  寄存器原始值全 0 → 根因在 SPI/硬件层，而非软件换算\n" COLOR_RESET);
    else if (raw_stuck)
        printf(COLOR_RED "    ⚠  寄存器值全 0xFF → SPI MISO 线可能悬空\n" COLOR_RESET);
    else
        printf(COLOR_GREEN "    ✓  寄存器原始值非零，硬件读取正常\n" COLOR_RESET);

    // Layer 5: 换算成物理量
    uint8_t ctrl1 = reg_read(REG_CTRL1_XL);
    uint8_t ctrl2 = reg_read(REG_CTRL2_G);
    float accel_scale = accel_scale_from_ctrl(ctrl1);
    float gyro_scale = gyro_scale_from_ctrl(ctrl2);
    float gx = rx_g * gyro_scale / 1000.0f;
    float gy = ry_g * gyro_scale / 1000.0f;
    float gz = rz_g * gyro_scale / 1000.0f;
    float ax = rx_a * accel_scale / 1000.0f;
    float ay = ry_a * accel_scale / 1000.0f;
    float az = rz_a * accel_scale / 1000.0f;
    float temp_c = raw_temp / kTempScale + kTempOffset;

    printf("\n  [Layer 5] 换算后 (物理量, 坐标变换前)\n");
    printf("    Gyro  (deg/s): X=%8.3f  Y=%8.3f  Z=%8.3f\n", gx, gy, gz);
    printf("    Accel (g)    : X=%8.4f  Y=%8.4f  Z=%8.4f\n", ax, ay, az);
    printf("    Temp  (°C)   : %.2f\n", temp_c);

    float accel_norm = sqrtf(ax*ax + ay*ay + az*az);
    if (fabsf(accel_norm) < 0.01f)
        printf(COLOR_YELLOW "    ⚠  Accel norm ≈ 0，静止状态下应约为 1g\n" COLOR_RESET);
    else
        printf(COLOR_GREEN "    ✓  Accel norm = %.4f g\n" COLOR_RESET, accel_norm);

    if (temp_c < -10.0f || temp_c > 85.0f)
        printf(COLOR_YELLOW "    ⚠  温度值异常 (%.2f°C)，可能读取不正确\n" COLOR_RESET, temp_c);
    else
        printf(COLOR_GREEN "    ✓  温度值正常 (%.2f°C)\n" COLOR_RESET, temp_c);

    // Layer 6: 坐标变换
    float gx2 = gx, gy2 = gy, gz2 = gz;
    float ax2 = ax, ay2 = ay, az2 = az;
    coord_transform_accel(sample_type, ax2, ay2, az2);
    coord_transform_gyro(sample_type,  gx2, gy2, gz2);

    printf("\n  [Layer 6] 坐标变换后 (sample_type=%s)\n", sample_type.c_str());
    printf("    Gyro  (deg/s): X=%8.3f  Y=%8.3f  Z=%8.3f\n", gx2, gy2, gz2);
    printf("    Accel (g)    : X=%8.4f  Y=%8.4f  Z=%8.4f\n", ax2, ay2, az2);
}

// ============================================================
// 实时监控模式
// ============================================================
static void monitor_loop(const std::string& sample_type, int hz) {
    uint8_t ctrl1 = reg_read(REG_CTRL1_XL);
    uint8_t ctrl2 = reg_read(REG_CTRL2_G);
    float accel_scale = accel_scale_from_ctrl(ctrl1);
    float gyro_scale = gyro_scale_from_ctrl(ctrl2);
    printf(COLOR_BOLD
           "\n[Monitor] 实时监控 %dHz，Ctrl+C 退出\n"
           "  当前量程: Accel ±%dg, Gyro ±%d dps\n"
           "  格式: Gyro(deg/s) X Y Z | Accel(g) X Y Z | Temp(°C) | STATUS\n"
           COLOR_RESET, hz, accel_range_from_ctrl(ctrl1), gyro_range_from_ctrl(ctrl2));
    printf("%-10s  %8s %8s %8s  |  %8s %8s %8s  |  %6s  | %s\n",
           "sample#", "Gx", "Gy", "Gz", "Ax", "Ay", "Az", "Temp", "STATUS");
    printf("%s\n", std::string(88, '-').c_str());

    int interval_us = 1000000 / hz;
    int count = 0;
    while (g_running) {
        uint8_t status = reg_read(REG_STATUS_REG);

        int16_t rx_g, ry_g, rz_g, rx_a, ry_a, rz_a;
        read_raw_xyz(REG_OUTX_L_G,  rx_g, ry_g, rz_g);
        read_raw_xyz(REG_OUTX_L_XL, rx_a, ry_a, rz_a);
        uint8_t tl = reg_read(REG_OUT_TEMP_L);
        uint8_t th = reg_read(REG_OUT_TEMP_H);
        int16_t rt = (int16_t)((th << 8) | tl);

        float gx = rx_g * gyro_scale / 1000.0f;
        float gy = ry_g * gyro_scale / 1000.0f;
        float gz = rz_g * gyro_scale / 1000.0f;
        float ax = rx_a * accel_scale / 1000.0f;
        float ay = ry_a * accel_scale / 1000.0f;
        float az = rz_a * accel_scale / 1000.0f;
        float temp = rt / kTempScale + kTempOffset;

        coord_transform_accel(sample_type, ax, ay, az);
        coord_transform_gyro(sample_type,  gx, gy, gz);

        // 若全零用红色高亮
        bool all_zero = (rx_g == 0 && ry_g == 0 && rz_g == 0 &&
                         rx_a == 0 && ry_a == 0 && rz_a == 0);
        const char* row_color = all_zero ? COLOR_RED : COLOR_RESET;

        printf("%s%-10d  %8.3f %8.3f %8.3f  |  %8.4f %8.4f %8.4f  |  %6.2f  | 0x%02X%s\n",
               row_color, count++,
               gx, gy, gz, ax, ay, az, temp, status,
               COLOR_RESET);
        fflush(stdout);
        usleep(interval_us);
    }
    printf("\nMonitor stopped.\n");
}

// ============================================================
// 打印诊断建议
// ============================================================
static void print_diagnosis_hint() {
    printf(COLOR_BOLD "\n[诊断建议]\n" COLOR_RESET);
    printf("  根据上方各层结果，常见根因及修复建议：\n\n");
    printf("  WHO_AM_I 读错\n");
    printf("    → SPI 设备路径错误 / CS 未正确拉低 / 供电异常\n");
    printf("    → 检查: ls /dev/spidev*  / 量测 VDD_IMU 电压\n\n");
    printf("  CTRL 寄存器全 0\n");
    printf("    → Init() 未被调用，或 WriteRegister 没有成功（SPI Write CS 极性问题）\n");
    printf("    → 尝试: 停止 IMU 服务后执行 ./imu_diag <spi_dev> restore\n\n");
    printf("  STATUS_REG XLDA/GDA = 0\n");
    printf("    → ODR 可能为 0 (PowerDown 模式) / BDU 未使能导致数据锁定\n");
    printf("    → 检查 CTRL1_XL 高4位 != 0, CTRL3_C bit[6]=1\n\n");
    printf("  原始寄存器全 0，WHO_AM_I 正常\n");
    printf("    → BDU=1 时若未读完上一帧，输出寄存器被锁定\n");
    printf("    → 或者 ODR 太低 / 采样时机不对，多读几次观察 monitor 输出\n\n");
    printf("  原始值非零但 ROS topic 全 0\n");
    printf("    → 换算/坐标变换没问题，检查 ROS 消息赋值代码\n");
    printf("    → 检查 imu_test.cpp 中 msg.angular_velocity / linear_acceleration 的赋值字段\n\n");
}

// ============================================================
// 命令行帮助
// ============================================================
static void print_usage(const char* program) {
    printf(
        "Usage:\n"
        "  %s [spi_dev] [sample_type] [hz]       诊断并实时监控\n"
        "  %s <spi_dev> range show               查看当前量程\n"
        "  %s <spi_dev> range accel <2|4|8|16>\n"
        "  %s <spi_dev> range gyro <125|250|500|1000|2000|4000>\n"
        "  %s <spi_dev> restore                  恢复机器人默认配置\n"
        "\n"
        "修改寄存器前必须停止 imu_node/lowlevel_service，避免并发访问 SPI。\n",
        program, program, program, program, program);
}

static bool command_device_check() {
    uint8_t id = reg_read(REG_WHO_AM_I);
    if (id != 0x6B) {
        fprintf(stderr, COLOR_RED
                "WHO_AM_I mismatch: got 0x%02X, expected 0x6B; refusing to write\n"
                COLOR_RESET, id);
        return false;
    }
    return true;
}

// ============================================================
// main
// ============================================================
int main(int argc, char* argv[]) {
    const char* spi_dev = "/dev/spidev0.0";
    std::string sample_type = "bsample";
    int monitor_hz = 20;

    if (argc >= 2 &&
        (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0)) {
        print_usage(argv[0]);
        return 0;
    }

    if (argc >= 2) spi_dev      = argv[1];

    signal(SIGINT, sig_handler);

    if (!spi_open(spi_dev)) return 1;

    if (argc >= 3 && strcmp(argv[2], "range") == 0) {
        if (argc == 4 && strcmp(argv[3], "show") == 0) {
            if (!command_device_check()) {
                close(spi_fd);
                return 1;
            }
            print_range_config();
            close(spi_fd);
            return 0;
        }
        if (argc != 5 ||
            (strcmp(argv[3], "accel") != 0 && strcmp(argv[3], "gyro") != 0)) {
            print_usage(argv[0]);
            close(spi_fd);
            return 2;
        }

        int range = 0;
        if (!parse_int(argv[4], range)) {
            fprintf(stderr, "Invalid numeric range: %s\n", argv[4]);
            close(spi_fd);
            return 2;
        }
        if (!command_device_check()) {
            close(spi_fd);
            return 1;
        }

        printf(COLOR_YELLOW
               "Warning: ensure imu_node/lowlevel_service is stopped before writing.\n"
               COLOR_RESET);
        bool ok = strcmp(argv[3], "accel") == 0
                      ? set_accel_range(range)
                      : set_gyro_range(range);
        if (ok) print_range_config();
        close(spi_fd);
        return ok ? 0 : 1;
    }

    if (argc >= 3 &&
        (strcmp(argv[2], "restore") == 0 || strcmp(argv[2], "init") == 0)) {
        if (argc != 3) {
            print_usage(argv[0]);
            close(spi_fd);
            return 2;
        }
        if (!command_device_check()) {
            close(spi_fd);
            return 1;
        }
        printf(COLOR_YELLOW
               "Warning: ensure imu_node/lowlevel_service is stopped before restoring.\n"
               COLOR_RESET);
        bool ok = restore_default_config();
        close(spi_fd);
        return ok ? 0 : 1;
    }

    if (argc >= 3) sample_type = argv[2];
    if (argc >= 4) monitor_hz = atoi(argv[3]);
    if (monitor_hz <= 0 || monitor_hz > 200) monitor_hz = 20;

    printf(COLOR_BOLD COLOR_CYAN
           "========================================\n"
           "  ASM330LHHTR IMU 全链路诊断工具\n"
           "  SPI: %s   sample_type: %s\n"
           "========================================\n"
           COLOR_RESET, spi_dev, sample_type.c_str());

    // ---- 逐层检查 ----
    bool spi_ok = check_who_am_i();
    if (!spi_ok) {
        printf(COLOR_RED "\n  SPI 通信失败，跳过后续检查，请先排查硬件连接\n" COLOR_RESET);
        close(spi_fd);
        return 1;
    }

    check_ctrl_regs();
    check_status_reg();
    check_one_sample(sample_type);
    print_diagnosis_hint();

    // ---- 实时监控 ----
    if (g_running) {
        printf(COLOR_BOLD "\n进入实时监控模式 (%dHz)，Ctrl+C 退出...\n" COLOR_RESET, monitor_hz);
        monitor_loop(sample_type, monitor_hz);
    }

    close(spi_fd);
    return 0;
}
