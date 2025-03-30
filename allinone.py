import argparse
import sys
import time
import threading
import queue
import random
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

import streamer
#from streamer import StreamingOutput, start_streaming_server, armed_state
from HWServo import HWServo

last_boxes = None
last_scores = None
last_keypoints = None
WINDOW_SIZE_H_W = (480, 640)

LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6

pitchServo = HWServo(pwm_chip=2, pwm_channel=2, min_duty=1000000, max_duty=2000000)
yawServo =   HWServo(pwm_chip=2, pwm_channel=1, min_duty=500000,  max_duty=2500000)
fireServo =  HWServo(pwm_chip=2, pwm_channel=0, min_duty=500000,  max_duty=2500000)

def init_servos():
    pitchServo.mid()
    yawServo.mid()
    fireServo.mid()

def close_servos():
    pitchServo.cleanup()
    yawServo.cleanup()
    fireServo.cleanup()

# Create a queue to hold the data
data_queue = queue.Queue()

last_aim_timestamp = None
def aim(aimPointX, aimPointY, fire):
    global last_aim_timestamp
    global data_queue
    if not fire and last_aim_timestamp is not None and time.time() - last_aim_timestamp < 0.2:
        return
    last_aim_timestamp = time.time()
    data_queue.put((aimPointX, aimPointY, fire and streamer.armed_state))

search_point = 0
search_count = 0
search_coords = [
    (-45, -90),
    (-45, -45),
    (-45, 0),
    (-45, 45),
    (-45, 90),
    (-20, 90),
    (-20, 45),
    (-20, 0),
    (-20, -45),
    (-20, -90),
    (0, -90),
    (0, -45),
    (0, 0),
    (0, 45),
    (0, 90),
    (20, 90),
    (20, 45),
    (20, 0),
    (20, -45),
    (20, -90),
    (45, -90),
    (45, -45),
    (45, 0),
    (45, 45),
    (45, 90)
]
def aim_turret_thread():
    global data_queue
    global search_point
    global search_count
    while True:
        aimPointX, aimPointY, fire = data_queue.get()
        if aimPointX is None and aimPointY is None:
            break
        
        if aimPointX == -1 and aimPointY == -1:
            search = True
            search_count += 1
            if search_count > 3:
                search_count = 0
                yawServo.set_angle(search_coords[search_point][1])
                pitchServo.set_angle(search_coords[search_point][0])
                search_point += 1
                if search_point >= len(search_coords):
                    search_point = 0
        else:
            print(aimPointX, aimPointY, fire)
            # Calculate the proportional adjustment for yaw
            if aimPointX < 315 or aimPointX > 325:
                yaw_adjustment = (aimPointX - 320) / 320 * 45
                yawServo.adjust_angle(yaw_adjustment)

            # Calculate the proportional adjustment for pitch
            if aimPointY < 235 or aimPointY > 245:
                pitch_adjustment = (240 - aimPointY) / 240 * 45
                pitchServo.adjust_angle(pitch_adjustment)

            if fire:
                fireServo.max()
                sleep(0.22)
            fireServo.mid()
        


def ai_output_tensor_parse(metadata: dict):
    """Parse the output tensor into a number of detected objects, scaled to the ISP output."""
    global last_boxes, last_scores, last_keypoints
    np_outputs = imx500.get_outputs(metadata=metadata, add_batch=True)
    if np_outputs is not None:
        keypoints, scores, boxes = postprocess_higherhrnet(outputs=np_outputs,
                                                           img_size=WINDOW_SIZE_H_W,
                                                           img_w_pad=(0, 0),
                                                           img_h_pad=(0, 0),
                                                           detection_threshold=args.detection_threshold,
                                                           network_postprocess=True)

        if scores is not None and len(scores) > 0:
            last_keypoints = np.reshape(np.stack(keypoints, axis=0), (len(scores), 17, 3))
            last_boxes = [np.array(b) for b in boxes]
            last_scores = np.array(scores)
    return last_boxes, last_scores, last_keypoints


def draw(request: CompletedRequest, boxes, scores, keypoints, aimPointX, aimPointY, fire, stream='main'):
    """Draw the detections for this request onto the ISP output."""
    with MappedArray(request, stream) as m:
        # if boxes is not None and len(boxes) > 0:
        #     drawer.annotate_image(m.array, boxes, scores,
        #                           np.zeros(scores.shape), keypoints, args.detection_threshold,
        #                           args.detection_threshold, request.get_metadata(), picam2, stream)
        if keypoints is not None:
            for kp in keypoints:
                drawer.draw_keypoints(m.array, kp, 0.05, request.get_metadata(), picam2, stream)

        if aimPointX != -1 and aimPointY != -1:
            cv2.circle(m.array, (aimPointX, aimPointY), 5, (0, 255, 0), -1)
            cv2.line(m.array, (aimPointX, 0), (aimPointX, WINDOW_SIZE_H_W[0]), (0, 255, 0), 1)
            cv2.line(m.array, (0, aimPointY), (WINDOW_SIZE_H_W[1], aimPointY), (0, 255, 0), 1)
            # Target square
            cv2.rectangle(m.array, (315, 235), (325, 245), (0, 255, 0), 1)


target = 0
def picamera2_pre_callback(request: CompletedRequest):
    global target
    """Analyse the detected objects in the output tensor and draw them on the main output image."""
    boxes, scores, keypoints = ai_output_tensor_parse(request.get_metadata())
    #print(boxes, scores, keypoints)
    aimPointX = -1
    aimPointY = -1
    if keypoints is not None:
        if target > len(keypoints):
            target = 0
        target_keypoints = keypoints[target]
        if target_keypoints[LEFT_SHOULDER][2] > 0.1 and target_keypoints[RIGHT_SHOULDER][2] > 0.1:
            aimPointX = int((target_keypoints[LEFT_SHOULDER][0] + target_keypoints[RIGHT_SHOULDER][0]) / 2)
            aimPointY = int((target_keypoints[LEFT_SHOULDER][1] + target_keypoints[RIGHT_SHOULDER][1]) / 2)
    fire, aimPointX, aimPointY = update_state(target, aimPointX, aimPointY)
    draw(request, boxes, scores, keypoints, aimPointX, aimPointY, fire)
    aim(aimPointX, aimPointY, fire)

locked_time = None
search_aim_point = [320, 240]
search_direction_x = 1
search_direction_1 = 1
def update_state(target, aimPointX, aimPointY):
    global locked_time
    global search_aim_point
    fire = False
    search = False
    locked = (aimPointX > 315 and aimPointX < 325) and (aimPointY > 235 and aimPointY < 245)
    if locked:
        if locked_time is None:
            locked_time = time.time()
        elif time.time() - locked_time > 1.5:
            fire = True
            locked_time = None
            target += 1
    return fire, aimPointX, aimPointY

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


def get_drawer():
    categories = intrinsics.labels
    categories = [c for c in categories if c and c != "-"]
    return COCODrawer(categories, imx500, needs_rescale_coords=False)


if __name__ == "__main__":
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

    drawer = get_drawer()

    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(controls={'FrameRate': intrinsics.inference_rate}, transform=Transform(hflip=True), buffer_count=12)

    imx500.show_network_fw_progress_bar()
    picam2.start(config, show_preview=False)
    imx500.set_auto_aspect_ratio()
    picam2.pre_callback = picamera2_pre_callback

    # Send to stream
    #output = StreamingOutput()
    #picam2.start_recording(JpegEncoder(), FileOutput(output))

    init_servos()

    # Start the aim_turret thread
    turret_thread = threading.Thread(target=aim_turret_thread)
    turret_thread.start()

    output = streamer.StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))

    try:
        streamer.start_streaming_server(output)
        # while True:
        #     sleep(1)
    except KeyboardInterrupt:
        # Stop the turret thread
        data_queue.put((None, None, None))
        turret_thread.join()
    finally:
        close_servos()
        picam2.stop()
        picam2.close()
        print("Exiting")