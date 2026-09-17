#!/usr/bin/env python3
"""Passive AprilTag circle21h7 benchmark on ROS/Aorta infrared MCAP frames.

The reported pose is tag-in-camera, not robot-in-dock. Robot/dock pose requires
verified extrinsics and dock geometry. No GPIO or camera controls are performed.
"""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
import subprocess

import cv2
import numpy as np
from sensor_tools import aorta
from sensor_tools.calibration import cameras, load
from sensor_tools.images import raw_image, save_image
from sensor_tools.mcap import iter_records, source_time_ns


def benchmark(path, output, *, topic='/infrared_camera/image_raw', target_id=2,
              margin_threshold=50, calibration=None, tag_size=None, max_frames=1000,
              save_failed=False, save_annotated=False, annotated_interval=1, detector=None):
    if detector is None:
        from pupil_apriltags import Detector
        detector = Detector(families='tagCircle21h7', nthreads=1, quad_decimate=1.0)
    if max_frames < 1 or annotated_interval < 1 or margin_threshold < 0:
        raise ValueError('invalid frame count, annotation interval or margin threshold')
    params = None
    if calibration:
        if tag_size is None or tag_size <= 0:
            raise ValueError('pose estimation requires --tag-size in meters')
        params = cameras(load(calibration))['infrared']
    elif tag_size is not None:
        raise ValueError('--tag-size requires --calibration')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows, margins = [], []
    for record in iter_records(path, [topic]):
        gray = raw_image(record.data, grayscale=True)
        camera_params = None
        if params:
            if gray.shape != (params['height'], params['width']):
                raise ValueError('image resolution differs from calibration; refusing implicit rescaling')
            K, D = params['K'], params['D']
            gray = (cv2.fisheye.undistortImage(gray, K, D, Knew=K) if params['model'] == 'equidistant'
                    else cv2.undistort(gray, K, D, newCameraMatrix=K))
            camera_params = [K[0, 0], K[1, 1], K[0, 2], K[1, 2]]
        detections = detector.detect(np.ascontiguousarray(gray), estimate_tag_pose=bool(params),
                                     camera_params=camera_params, tag_size=tag_size)
        targets = [d for d in detections if d.tag_id == target_id]
        best = max(targets, key=lambda d: d.decision_margin) if targets else None
        detected = best is not None and best.decision_margin >= margin_threshold
        row = dict(frame=len(rows), source_time_ns=source_time_ns(record.data, record.publish_time_ns),
                   log_time_ns=record.log_time_ns, publish_time_ns=record.publish_time_ns,
                   detection_count=len(detections), target_found=bool(targets), accepted=detected,
                   margin=float(best.decision_margin) if best else None,
                   tag_in_camera_x_m=None, tag_in_camera_y_m=None, tag_in_camera_z_m=None,
                   tag_in_camera_rotation=None, pose_error=None)
        if best:
            margins.append(float(best.decision_margin))
        if params and detected:
            translation = np.asarray(best.pose_t).ravel()
            rotation = np.asarray(best.pose_R)
            if not np.isfinite(translation).all() or not np.isfinite(rotation).all():
                raise ValueError('non-finite tag pose')
            row.update(zip(['tag_in_camera_x_m', 'tag_in_camera_y_m', 'tag_in_camera_z_m'], map(float, translation)))
            row['tag_in_camera_rotation'] = rotation.tolist()
            row['pose_error'] = float(best.pose_err)
        if save_failed and not detected:
            save_image(output / 'failed' / f'{len(rows):06d}.png', gray)
        if save_annotated and len(rows) % annotated_interval == 0:
            image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for detection in detections:
                color = (0, 255, 0) if detection.tag_id == target_id and detection.decision_margin >= margin_threshold else (0, 180, 255)
                corners = np.asarray(detection.corners).astype(np.int32)
                cv2.polylines(image, [corners], True, color, 2)
                cv2.putText(image, f'id={detection.tag_id} m={detection.decision_margin:.1f}',
                            tuple(corners[0]), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
            save_image(output / 'annotated' / f'{len(rows):06d}.png', image)
        rows.append(row)
        if len(rows) >= max_frames:
            break
    if not rows:
        raise ValueError('no infrared image frames found; camera registration is not image reception')
    with (output / 'frames.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    accepted = sum(row['accepted'] for row in rows)
    summary = dict(frames=len(rows), detected_frames=accepted, detection_rate=accepted / len(rows),
                   target_id=target_id, margin_threshold=margin_threshold, family='tagCircle21h7',
                   margin_mean=statistics.mean(margins) if margins else None,
                   margin_min=min(margins) if margins else None, margin_max=max(margins) if margins else None,
                   pose_frame='tag_in_camera' if params else 'not_estimated',
                   ir_light='unchanged / not measured', isp_status='not measured',
                   scope='detection measurement; no production equivalence or acceptance threshold inferred')
    (output / 'report.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcap', type=Path, help='offline file; omit for passive live capture')
    parser.add_argument('--topic', default='/infrared_camera/image_raw')
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--tag', default='default')
    parser.add_argument('--target-tag-id', type=int, default=2)
    parser.add_argument('--margin-threshold', type=float, default=50)
    parser.add_argument('--calibration', type=Path, help='calibration containing camera label infrared')
    parser.add_argument('--tag-size', type=float, help='physical tag size in meters under the AprilTag pose convention')
    parser.add_argument('--max-frames', type=int, default=1000)
    parser.add_argument('--save-failed-frames', action='store_true')
    parser.add_argument('--save-annotated', action='store_true')
    parser.add_argument('--annotated-interval', type=int, default=1)
    parser.add_argument('--image-save-dir', type=Path, default=Path('output/ir_bench'))
    args = parser.parse_args()
    label = re.sub(r'[^a-zA-Z0-9_.-]', '_', args.tag)
    output = args.image_save_dir / f'{datetime.now():%Y%m%d_%H%M%S_%f}_{label}'
    try:
        path = args.mcap or output / 'capture.mcap'
        if not args.mcap:
            aorta.capture(path, [args.topic], args.duration)
        summary = benchmark(path, output, topic=args.topic, target_id=args.target_tag_id,
            margin_threshold=args.margin_threshold, calibration=args.calibration, tag_size=args.tag_size,
            max_frames=args.max_frames, save_failed=args.save_failed_frames,
            save_annotated=args.save_annotated, annotated_interval=args.annotated_interval)
        print(json.dumps(summary, indent=2))
        print(f'Report: {output}')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
