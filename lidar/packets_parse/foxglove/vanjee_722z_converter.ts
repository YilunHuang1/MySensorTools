/**
 * Foxglove User Script — 万集 WLR-722Z 点云解析
 *
 * 订阅 /lidar_packets，实时解析为 /lidar_points (foxglove.PointCloud)
 * 在 Foxglove Desktop 的 3D panel 中直接可视化。
 *
 * 使用方法：
 *   1. 打开 Foxglove Desktop，加载含 /lidar_packets 的 mcap
 *   2. 左侧边栏点击 "</>" (User Scripts) 图标，或菜单 View → User Scripts
 *   3. 点击左上角 "+" 新建脚本，将本文件全部内容粘贴进去
 *   4. Ctrl+S 保存（顶部无红色报错即编译成功）
 *   5. 添加 3D panel，订阅 /lidar_points，点云即可显示
 *
 * 协议参考: vanjee_driver/decoder/decoder_vanjee_722z.hpp
 * 角度校准: Vanjee_722z_VA.csv (16 通道)
 */

import { Input, Message } from "./types.ts";

// ── 角度校准表 (来自 Vanjee_722z_VA.csv，CH0~CH15) ───────────────────────────
const CHANNEL_ANGLES: [number, number][] = [
  [ -0.25, -2.423793797],
  [  2.45,  1.567974548],
  [  5.15, -2.476401604],
  [  7.85,  1.564088422],
  [ 10.55, -2.556836084],
  [ 13.25,  1.570029870],
  [ 15.95, -2.660435648],
  [ 18.65,  1.577551370],
  [ 21.35, -2.792973984],
  [ 24.05,  1.588058484],
  [ 26.75, -2.959146469],
  [ 29.45,  1.602694375],
  [ 32.15, -3.165727619],
  [ 34.85,  1.624512060],
  [ 37.55, -3.422034977],
  [ 40.25,  1.671322722],
];

// ── 物理参数 ──────────────────────────────────────────────────────────────────
const OPTCENT_ARG_DEG = 21.570;
const OPTCENT_L       = 0.02067;
const OPTCENT_Z       = 0.00795;
const DISTANCE_RES    = 0.002;
const DISTANCE_MIN    = 0.01;
const DISTANCE_MAX    = 100.0;

// ── User Script 元数据 ────────────────────────────────────────────────────────
export const inputs = ["/lidar_packets"];
export const output = "/lidar_points";

export const datatypes = new Map([
  ["foxglove.PointCloud", { definitions: [
    { name: "timestamp",    type: "time"   },
    { name: "frame_id",     type: "string" },
    { name: "pose",         type: "foxglove.Pose",               isComplex: true },
    { name: "point_stride", type: "uint32" },
    { name: "fields",       type: "foxglove.PackedElementField", isArray: true, isComplex: true },
    { name: "data",         type: "uint8",  isArray: true },
  ]}],
  ["foxglove.Pose", { definitions: [
    { name: "position",    type: "foxglove.Vector3",    isComplex: true },
    { name: "orientation", type: "foxglove.Quaternion", isComplex: true },
  ]}],
  ["foxglove.Vector3", { definitions: [
    { name: "x", type: "float64" },
    { name: "y", type: "float64" },
    { name: "z", type: "float64" },
  ]}],
  ["foxglove.Quaternion", { definitions: [
    { name: "x", type: "float64" },
    { name: "y", type: "float64" },
    { name: "z", type: "float64" },
    { name: "w", type: "float64" },
  ]}],
  ["foxglove.PackedElementField", { definitions: [
    { name: "name",   type: "string" },
    { name: "offset", type: "uint32" },
    { name: "type",   type: "uint32" },
  ]}],
]);

// ── CRC32/MPEG-2 ──────────────────────────────────────────────────────────────
function crc32mpeg2(buf: Uint8Array, len: number): number {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < len; i++) {
    crc ^= (buf[i]! << 24);
    for (let j = 0; j < 8; j++) {
      crc = (crc & 0x80000000)
        ? (((crc << 1) ^ 0x04C11DB7) >>> 0)
        : ((crc << 1) >>> 0);
    }
  }
  return crc >>> 0;
}

// ── CDR 解析：提取 VanjeelidarPacket.data 字节数组 ───────────────────────────
function parseCDR(raw: Uint8Array): Uint8Array | null {
  if (raw.length < 20) return null;
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  let offset = 4;
  offset += 8;                                      // stamp.sec + stamp.nanosec
  const strLen = view.getUint32(offset, true);
  offset += 4 + strLen;
  offset = (offset + 3) & ~3;                       // 4-byte align
  const dataLen = view.getUint32(offset, true);
  offset += 4;
  return raw.subarray(offset, offset + dataLen);
}

// ── 从 data 字节流扫描 80 字节点云子包 ───────────────────────────────────────
function extractSubPackets(data: Uint8Array): Uint8Array[] {
  const result: Uint8Array[] = [];
  let i = 0;
  while (i < data.length - 1) {
    if (data[i] !== 0xEE) { i++; continue; }
    if (data[i + 1] === 0xFF) {
      if (i + 6 > data.length) break;
      const dtype = data[i + 5]!;
      if (dtype === 0x00 && i + 80 <= data.length) {
        result.push(data.subarray(i, i + 80));
        i += 80;
      } else if (dtype === 0x01 && i + 34 <= data.length) {
        i += 34;
      } else { i++; }
    } else if (data[i + 1] === 0xDD) {
      i += (i + 41 <= data.length) ? 41 : 1;
    } else { i++; }
  }
  return result;
}

// ── 解析单个 80 字节点云包 → {azimuth01, 点列表} ─────────────────────────────
type Point3 = { x: number; y: number; z: number; intensity: number };
type DecodeResult = { azimuth01: number; points: Point3[] };

function decodePacket(pkt: Uint8Array): DecodeResult | null {
  if (pkt.length !== 80 || pkt[0] !== 0xEE || pkt[1] !== 0xFF || pkt[5] !== 0x00) return null;
  const view = new DataView(pkt.buffer, pkt.byteOffset, pkt.byteLength);
  if (crc32mpeg2(pkt, 76) !== view.getUint32(76, true)) return null;

  const azimuth01  = view.getUint16(16, true) % 36000;
  const azimuthDeg = azimuth01 * 0.01;
  const optcentHor = (azimuthDeg + OPTCENT_ARG_DEG + 360) % 360;
  const sinOpt = Math.sin(optcentHor * Math.PI / 180);
  const cosOpt = Math.cos(optcentHor * Math.PI / 180);

  const points: Point3[] = [];
  for (let chan = 0; chan < 16; chan++) {
    const off          = 18 + chan * 3;
    const distRaw      = view.getUint16(off, true);
    const reflectivity = pkt[off + 2]!;
    const distance     = distRaw * DISTANCE_RES;
    if (distance < DISTANCE_MIN || distance > DISTANCE_MAX) continue;

    const [vertDeg, horizOffDeg] = CHANNEL_ANGLES[chan]!;
    const horizFinal = (horizOffDeg + azimuthDeg + 360) % 360;
    const sinV = Math.sin(vertDeg    * Math.PI / 180);
    const cosV = Math.cos(vertDeg    * Math.PI / 180);
    const sinH = Math.sin(horizFinal * Math.PI / 180);
    const cosH = Math.cos(horizFinal * Math.PI / 180);
    const xy   = distance * cosV;
    points.push({
      x:         xy * sinH + OPTCENT_L * sinOpt,
      y:         xy * cosH + OPTCENT_L * cosOpt,
      z:         distance * sinV + OPTCENT_Z,
      intensity: reflectivity,
    });
  }
  return { azimuth01, points };
}

// ── 帧累积状态（模块级变量，跨消息持久化）────────────────────────────────────
// 官方推荐：用模块顶层 let 变量保存跨调用状态（而非 globalThis）
let _accumPoints: Point3[] = [];
let _frameTimestamp: { sec: number; nsec: number } | null = null;
let _prevAzimuthTrans = -1;

// ── 点列表 → foxglove.PointCloud 消息 ────────────────────────────────────────
function buildPointCloud(
  points: Point3[],
  timestamp: { sec: number; nsec: number },
): Message<"foxglove.PointCloud"> {
  const POINT_STEP = 16;
  const buf = new ArrayBuffer(points.length * POINT_STEP);
  const dv  = new DataView(buf);
  for (let i = 0; i < points.length; i++) {
    const off = i * POINT_STEP;
    const p   = points[i]!;
    dv.setFloat32(off +  0, p.x,         true);
    dv.setFloat32(off +  4, p.y,         true);
    dv.setFloat32(off +  8, p.z,         true);
    dv.setFloat32(off + 12, p.intensity, true);
  }
  return {
    timestamp,
    frame_id:     "lidar",
    pose: {
      position:    { x: 0, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
    point_stride: POINT_STEP,
    fields: [
      { name: "x",         offset:  0, type: 7 },
      { name: "y",         offset:  4, type: 7 },
      { name: "z",         offset:  8, type: 7 },
      { name: "intensity", offset: 12, type: 7 },
    ],
    data: new Uint8Array(buf),
  };
}

// ── Foxglove User Script 入口 ─────────────────────────────────────────────────
//
// 帧切割逻辑（与 C++ SplitStrategyByAngle 一致）：
//   azimuth_trans = (azimuth + 60) % 36000
//   当 azimuth_trans < prevAzimuthTrans 时，表示过了 0° → 新帧开始
//
// 一帧约 600 个子包（360° / 0.6°），凑满一整圈后才发出，保证 5 Hz 完整帧。
//
export default function script(
  event: Input<"/lidar_packets">,
): Message<"foxglove.PointCloud"> | undefined {
  const raw       = event.message.data as Uint8Array;
  const dataBytes = parseCDR(raw);
  if (!dataBytes || dataBytes.length === 0) return undefined;

  const subPkts = extractSubPackets(dataBytes);
  if (subPkts.length === 0) return undefined;

  let completedFrame: Message<"foxglove.PointCloud"> | undefined;

  for (const pkt of subPkts) {
    const result = decodePacket(pkt);
    if (!result) continue;

    const { points, azimuth01 } = result;

    if (_frameTimestamp === null) {
      _frameTimestamp = event.receiveTime;
    }

    const azimuthTrans = (azimuth01 + 60) % 36000;
    if (_prevAzimuthTrans >= 0 && azimuthTrans < _prevAzimuthTrans) {
      // 帧切割：发出完整帧，重置累积
      if (_accumPoints.length > 0 && _frameTimestamp !== null) {
        completedFrame = buildPointCloud(_accumPoints, _frameTimestamp);
      }
      _accumPoints    = points.slice();
      _frameTimestamp = event.receiveTime;
    } else {
      for (const p of points) _accumPoints.push(p);
    }

    _prevAzimuthTrans = azimuthTrans;
  }

  return completedFrame;
}
