import argparse
import sys
import time
import threading
import queue
from time import sleep

import cv2
import numpy as np

from picamera2 import CompletedRequest, MappedArray, Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform
from picamera2.devices.imx500 import IMX500, NetworkIntrinsics
from picamera2.devices.imx500.postprocess import COCODrawer, PARTS
from picamera2.devices.imx500.postprocess_highernet import \
    postprocess_higherhrnet

from turret_state_machine import TurretStateMachine, TurretState
from HWServo import HWServo
from HATServo import HATServo
import streamer

WINDOW_SIZE_H_W = (480, 640)

# Servo initialization
# pitch_servo = HWServo(pwm_chip=0, pwm_channel=2, min_duty=1000000, max_duty=2000000)
# yaw_servo = HWServo(pwm_chip=0, pwm_channel=1, min_duty=500000, max_duty=2500000)
# fire_servo = HWServo(pwm_chip=0, pwm_channel=0, min_duty=500000, max_duty=2500000)
pitch_servo = HATServo(channel=0, min_pulse=1000, max_pulse=2000)
yaw_servo = HATServo(channel=1)
fire_servo = HATServo(channel=2)

# Initialize state machine
turret = TurretStateMachine(pitch_servo, yaw_servo, fire_servo)

keypoints = None
boxes = None
scores = None
imx500 = None
drawer = None
picam2 = None

def camera_callback(request: CompletedRequest):
    """Parse AI metadata and update target information."""
    """Parse the output tensor into a number of detected objects, scaled to the ISP output."""
    global imx500, keypoints, boxes, scores
    np_outputs = imx500.get_outputs(metadata=request.get_metadata(), add_batch=True)
    if np_outputs is not None:
        raw_keypoints, raw_scores, raw_boxes = postprocess_higherhrnet(outputs=np_outputs,
                                                           img_size=WINDOW_SIZE_H_W,
                                                           img_w_pad=(0, 0),
                                                           img_h_pad=(0, 0),
                                                           detection_threshold=args.detection_threshold,
                                                           network_postprocess=True)

        if raw_scores is not None and len(raw_scores) > 0:
            keypoints = np.reshape(np.stack(raw_keypoints, axis=0), (len(raw_scores), 17, 3))
            boxes = [np.array(b) for b in raw_boxes]
            scores = np.array(raw_scores)
        else:
            keypoints = None
            boxes = None
            scores = None
    
    draw(request)

def draw(request: CompletedRequest, stream='main'):
    """Draw the detections for this request onto the ISP output."""
    global picam2, drawer
    with MappedArray(request, stream) as m:
        # if boxes is not None and len(boxes) > 0:
        #     drawer.annotate_image(m.array, boxes, scores,
        #                           np.zeros(scores.shape), keypoints, args.detection_threshold,
        #                           args.detection_threshold, request.get_metadata(), picam2, stream)
        if keypoints is not None:
            for kp in keypoints:
                drawer.draw_keypoints(m.array, kp, 0.05, request.get_metadata(), picam2, stream)

        if turret.aim_point is not None:
            aimPointX, aimPointY = turret.aim_point
            cv2.circle(m.array, (aimPointX, aimPointY), 5, (0, 255, 0), -1)
            cv2.line(m.array, (aimPointX, 0), (aimPointX, WINDOW_SIZE_H_W[0]), (0, 255, 0), 1)
            cv2.line(m.array, (0, aimPointY), (WINDOW_SIZE_H_W[1], aimPointY), (0, 255, 0), 1)
            # Target square
            color = (255, 0, 0) if turret.state == TurretState.FIRING  \
               else (0, 0, 255) if turret.state == TurretState.LOCKED  \
               else (0, 255, 0)
            cv2.rectangle(m.array, (320 - turret.AIM_WINDOW_SIZE, 240 - turret.AIM_WINDOW_SIZE), \
                                   (320 + turret.AIM_WINDOW_SIZE, 240 + turret.AIM_WINDOW_SIZE), \
                                   color,  1)

        # Draw the turret mode on the image
        cv2.putText(m.array, f"{turret.state.name}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Put arm/disarm text
        if turret.armed:
            cv2.putText(m.array, "ARMED", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        else:   
            cv2.putText(m.array, "DISARMED", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, help="Path of the model",
                        default="/usr/share/imx500-models/imx500_network_higherhrnet_coco.rpk")
    parser.add_argument("--fps", type=int, help="Frames per second")
    parser.add_argument("--detection-threshold", type=float, default=0.1,
                        help="Post-process detection threshold")
    parser.add_argument("--labels", type=str,
                        help="Path to the labels file")
    parser.add_argument("--print-intrinsics", action="store_true",
                        help="Print JSON network_intrinsics then exit")
    return parser.parse_args()

def get_drawer(intrinsics):
    categories = intrinsics.labels
    categories = [c for c in categories if c and c != "-"]
    return COCODrawer(categories, imx500, needs_rescale_coords=False)

def main():
    global imx500, drawer, args, keypoints, boxes, scores, picam2
    args = get_args()

    # This must be called before instantiation of Picamera2
    imx500 = IMX500(args.model)
    intrinsics = imx500.network_intrinsics
    if not intrinsics:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "pose estimation"
    elif intrinsics.task != "pose estimation":
        print("Network is not a pose estimation task", file=sys.stderr)
        exit()

    # Override intrinsics from args
    for key, value in vars(args).items():
        if key == 'labels' and value is not None:
            with open(value, 'r') as f:
                intrinsics.labels = f.read().splitlines()
        elif hasattr(intrinsics, key) and value is not None:
            setattr(intrinsics, key, value)

    # Defaults
    if intrinsics.inference_rate is None:
        intrinsics.inference_rate = 10
    if intrinsics.labels is None:
        with open("assets/coco_labels.txt", "r") as f:
            intrinsics.labels = f.read().splitlines()
    intrinsics.update_with_defaults()

    if args.print_intrinsics:
        print(intrinsics)
        exit()

    drawer = get_drawer(intrinsics)
    
    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(controls={'FrameRate': intrinsics.inference_rate}, transform=Transform(hflip=True), buffer_count=12)

    imx500.show_network_fw_progress_bar()
    picam2.start(config, show_preview=False)
    imx500.set_auto_aspect_ratio()
    picam2.pre_callback = camera_callback

    # Send to stream
    output = streamer.StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))

    # Initialize servos
    pitch_servo.mid()
    yaw_servo.mid()
    fire_servo.mid()

    # Start streaming server on a thread
    streamer_thread = threading.Thread(target=streamer.start_streaming_server, args=(output,))
    streamer_thread.start()

    try:
        while True:
            turret.update(keypoints, boxes, scores, streamer.armed_state)
            sleep(0.25)
    except KeyboardInterrupt:
        streamer.stop_streaming_server()
    finally:
        pitch_servo.cleanup()
        yaw_servo.cleanup()
        fire_servo.cleanup()
        picam2.stop()
        picam2.close()
        print("Exiting")

if __name__ == "__main__":
    main()