import base64
import ctypes
import importlib.util
import json
import yaml
import csv
from pathlib import Path

import cv2
import numpy as np
from mcap.writer import Writer
from pupil_apriltags.bindings import Detector, _ImageU8, _ApriltagFamily, _image_u8_get_array


def test_real_circle21h7_detector_end_to_end(tmp_path):
    detector = Detector(families='tagCircle21h7', quad_decimate=1.0)
    detector.libc.apriltag_to_image.restype = ctypes.POINTER(_ImageU8)
    detector.libc.apriltag_to_image.argtypes = [ctypes.POINTER(_ApriltagFamily), ctypes.c_int]
    pointer = detector.libc.apriltag_to_image(detector.tag_families['tagCircle21h7'], 2)
    try:
        tag = _image_u8_get_array(pointer).copy()
    finally:
        detector.libc.image_u8_destroy(pointer)
    canvas = np.full((480,640),255,np.uint8)
    canvas[90:390,170:470] = cv2.resize(tag,(300,300),interpolation=cv2.INTER_NEAREST)
    path = tmp_path/'image.mcap'
    with path.open('wb') as file:
        writer=Writer(file);writer.start()
        schema=writer.register_schema('foxglove.RawImage','jsonschema',b'{"type":"object"}')
        channel=writer.register_channel('aorta/default/pub/infrared_camera/image_raw','json',schema)
        for index, image in enumerate([canvas, np.full_like(canvas,255)]):
            payload=dict(timestamp=dict(sec=100,nsec=index*100000000),frame_id='infrared',width=640,height=480,
                         encoding='mono8',step=640,data=base64.b64encode(image.tobytes()).decode())
            writer.add_message(channel,100000000000+index*100000000,json.dumps(payload).encode(),100000000000+index*100000000)
        writer.finish()
    spec=importlib.util.spec_from_file_location('ir_bench',Path(__file__).resolve().parents[1]/'infrared/ir_qr_bench/ir_qr_bench.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.benchmark(path,tmp_path/'output',save_failed=True,save_annotated=True,detector=detector)
    assert report['frames']==2
    assert report['detected_frames']==1
    assert report['detection_rate']==.5
    assert len(list((tmp_path/'output/failed').glob('*.png')))==1
    assert len(list((tmp_path/'output/annotated').glob('*.png')))==2
    assert report['pose_frame']=='not_estimated'

    calibration = tmp_path / 'calibration.yaml'
    calibration.write_text(yaml.safe_dump({'cameras': [{'camera': {
        'label': 'infrared', 'type': 'pinhole', 'image_width': 640, 'image_height': 480,
        'intrinsics': {'data': [300., 300., 320., 240.]},
        'distortion': {'type': 'radial_tangential', 'parameters': {'data': [0., 0., 0., 0.]}}
    }}]}))
    pose_report = module.benchmark(path, tmp_path/'pose', calibration=calibration,
                                   tag_size=.1, detector=detector)
    assert pose_report['pose_frame'] == 'tag_in_camera'
    with (tmp_path/'pose/frames.csv').open() as stream:
        pose = next(csv.DictReader(stream))
    assert float(pose['tag_in_camera_z_m']) > 0
    assert np.isfinite(float(pose['pose_error']))
