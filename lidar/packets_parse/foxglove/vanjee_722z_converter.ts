/**
 * Foxglove User Script — 万集 WLR-722Z 点云解析
 *
 * 订阅 Aorta lidar_packets，实时解析为 /sensor_tools/lidar_points_preview (foxglove.PointCloud)
 * 在 Foxglove Desktop 的 3D panel 中直接可视化。
 *
 * 使用方法：
 *   1. 打开 Foxglove Desktop，加载含 /lidar_packets 的 mcap
 *   2. 左侧边栏点击 "</>" (User Scripts) 图标，或菜单 View → User Scripts
 *   3. 点击左上角 "+" 新建脚本，将本文件全部内容粘贴进去
 *   4. Ctrl+S 保存（顶部无红色报错即编译成功）
 *   5. 添加 3D panel，订阅 /sensor_tools/lidar_points_preview，点云即可显示
 *
 * 协议参考: vanjee_driver/decoder/decoder_vanjee_722z.hpp
 * 角度校准: Vanjee_722z_VA.csv (16 通道)
 */

import type { Input, Message } from "./types.ts";

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
// Set this exact recorded/bridge channel for your group; historical MCAP may use /lidar_packets.
export const inputs = ["aorta/default/pub/lidar_packets"];
export const output = "/sensor_tools/lidar_points_preview";

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

// Raw serial packets can span multiple Aorta/MCAP messages.
let pending = new Uint8Array(0);
function extractSubPackets(chunk: Uint8Array): Uint8Array[] {
  const data = new Uint8Array(pending.length + chunk.length);
  data.set(pending); data.set(chunk, pending.length);
  const result: Uint8Array[] = [];
  let i = 0;
  while (i + 2 <= data.length) {
    let length = 0;
    let points = false;
    if (data[i] === 0xEE && data[i + 1] === 0xDD) length = 41;
    else if (data[i] === 0xEE && data[i + 1] === 0xFF) {
      if (i + 6 > data.length) break;
      if (data[i + 5] === 0) { length = 80; points = true; }
      else if (data[i + 5] === 1) length = 34;
      else { i++; continue; }
    } else { i++; continue; }
    if (i + length > data.length) break;
    if (points) result.push(data.slice(i, i + length));
    i += length;
  }
  pending = data.slice(i);
  return result;
}

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

// Preview emits decoded chunks at receiveTime, not reconstructed production scans.
// This avoids silently dropping a second completed scan in one input message.
// The bundled calibration table is a reference; use the device table for metric work.
export default function script(
  event: Input<"aorta/default/pub/lidar_packets">,
): Message<"foxglove.PointCloud"> | undefined {
  const dataBytes = Uint8Array.from(event.message.data as Uint8Array);
  const points: Point3[] = [];
  for (const packet of extractSubPackets(dataBytes)) {
    const result = decodePacket(packet);
    if (result) points.push(...result.points);
  }
  return points.length ? buildPointCloud(points, event.receiveTime) : undefined;
}
