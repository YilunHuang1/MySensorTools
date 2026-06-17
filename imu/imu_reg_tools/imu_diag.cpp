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
#include <sstream>

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

// 换算系数（与 imu.cpp 保持一致）
static constexpr float kAccelScale = 0.122f;  // mg/LSB, ±4g
static constexpr float kGyroScale  = 8.75f;   // mdps/LSB, ±250dps
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

static void reg_write(uint8_t reg, uint8_t val) {
    uint8_t tx[2] = {(uint8_t)(reg & 0x7F), val};
    uint8_t rx[2] = {0};
    struct spi_ioc_transfer tr;
    memset(&tr, 0, sizeof(tr));
    tr.tx_buf        = (unsigned long)tx;
    tr.rx_buf        = (unsigned long)rx;
    tr.len           = 2;
    tr.speed_hz      = kSpiSpeed;
    tr.bits_per_word = kSpiBits;
    ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr);
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

    struct {
        uint8_t     addr;
        const char* name;
        uint8_t     expected;
        const char* note;
    } regs[] = {
        {REG_CTRL1_XL, "CTRL1_XL (0x10)", 0x48, "104Hz, ±4g"},
        {REG_CTRL2_G,  "CTRL2_G  (0x11)", 0x40, "104Hz, ±250dps"},
        {REG_CTRL3_C,  "CTRL3_C  (0x12)", 0x44, "BDU=1, IF_INC=1"},
    };

    for (auto& r : regs) {
        uint8_t v = reg_read(r.addr);
        char detail[128];
        bool ok = (v == r.expected);
        snprintf(detail, sizeof(detail), "读回 0x%02X (期望 0x%02X)  %s",
                 v, r.expected, r.note);
        print_check(r.name, ok, detail);
        if (!ok && v == 0x00)
            printf(COLOR_YELLOW "    提示: 寄存器为 0x00，Init() 未执行 或 复位后没有写入\n" COLOR_RESET);
    }

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
    int16_t rt_l, rt_h;

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
    float gx = rx_g * kGyroScale / 1000.0f;
    float gy = ry_g * kGyroScale / 1000.0f;
    float gz = rz_g * kGyroScale / 1000.0f;
    float ax = rx_a * kAccelScale / 1000.0f;
    float ay = ry_a * kAccelScale / 1000.0f;
    float az = rz_a * kAccelScale / 1000.0f;
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
    printf(COLOR_BOLD
           "\n[Monitor] 实时监控 %dHz，Ctrl+C 退出\n"
           "  格式: Gyro(deg/s) X Y Z | Accel(g) X Y Z | Temp(°C) | STATUS\n"
           COLOR_RESET, hz);
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

        float gx = rx_g * kGyroScale / 1000.0f;
        float gy = ry_g * kGyroScale / 1000.0f;
        float gz = rz_g * kGyroScale / 1000.0f;
        float ax = rx_a * kAccelScale / 1000.0f;
        float ay = ry_a * kAccelScale / 1000.0f;
        float az = rz_a * kAccelScale / 1000.0f;
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
    printf("    → 尝试: ./imu_reg_tool write 0x10 0x48 再重跑诊断\n\n");
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
// main
// ============================================================
int main(int argc, char* argv[]) {
    const char* spi_dev = "/dev/spidev0.0";
    std::string sample_type = "bsample";
    int monitor_hz = 20;

    if (argc >= 2) spi_dev      = argv[1];
    if (argc >= 3) sample_type  = argv[2];
    if (argc >= 4) monitor_hz   = atoi(argv[3]);
    if (monitor_hz <= 0 || monitor_hz > 200) monitor_hz = 20;

    signal(SIGINT, sig_handler);

    printf(COLOR_BOLD COLOR_CYAN
           "========================================\n"
           "  ASM330LHHTR IMU 全链路诊断工具\n"
           "  SPI: %s   sample_type: %s\n"
           "========================================\n"
           COLOR_RESET, spi_dev, sample_type.c_str());

    if (!spi_open(spi_dev)) return 1;

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
