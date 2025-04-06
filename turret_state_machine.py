import time
from enum import Enum, auto
from threading import Thread
from time import sleep
import numpy as np
from simple_pid import PID  # Import the PID library

class TurretState(Enum):
    SEARCHING = auto()
    TRACKING = auto()
    LOCKED = auto()
    FIRING = auto()

class TurretStateMachine:
    AIM_WINDOW_SIZE = 50
    DEFAULT_SEARCH_COORDS = [
        (-45, -90), (-45, -45), (-45, 0), (-45, 45), (-45, 90),
        (-20, 90), (-20, 45), (-20, 0), (-20, -45), (-20, -90),
        (0, -90), (0, -45), (0, 0), (0, 45), (0, 90),
        (20, 90), (20, 45), (20, 0), (20, -45), (20, -90),
        (45, -90), (45, -45), (45, 0), (45, 45), (45, 90)
    ]

    def __init__(self, pitch_servo, yaw_servo, fire_servo, search_coords=None):
        self.state = TurretState.SEARCHING
        self.pitch_servo = pitch_servo
        self.yaw_servo = yaw_servo
        self.fire_servo = fire_servo
        self.search_coords = search_coords or self.DEFAULT_SEARCH_COORDS
        self.search_index = 0
        self.locked_time = None
        self.target_found = False
        self.aim_point = (-1, -1)
        self.fire = False
        self.target = 0
        self.armed = False
        self.yaw_pid = PID(0.1, 0.01, 0.05, setpoint=320)  # PID for yaw (center X = 320)
        self.pitch_pid = PID(0.1, 0.01, 0.05, setpoint=240)  # PID for pitch (center Y = 240)
        self.yaw_pid.output_limits = (-20, 20)  # Limit yaw adjustments
        self.pitch_pid.output_limits = (-20, 20)  # Limit pitch adjustments

    def set_state(self, new_state):
        print(f"Transitioning to state: {new_state}")
        self.state = new_state

    def update(self, keypoints, boxes, scores, armed_state):
        self.keypoints = keypoints
        self.boxes = boxes
        self.scores = scores
        self.armed = armed_state
        self.target_found = scores is not None and np.any(scores > 0.1)
        if self.target_found:
            self.update_aimpoint()
        else:
            self.aim_point = (-1, -1)
        state_handlers = {
            TurretState.SEARCHING: self.search,
            TurretState.TRACKING: self.track,
            TurretState.LOCKED: self.lock,
            TurretState.FIRING: self.fire_turret,
        }
        handler = state_handlers.get(self.state)
        if handler:
            handler()

    searchDeltaX = 5
    searchDeltaY = 5
    def search(self):
        if self.target_found:
            self.set_state(TurretState.TRACKING)
        else:
            if(self.yaw_servo.get_angle() + self.searchDeltaX > 55 or
                self.yaw_servo.get_angle() + self.searchDeltaX < -55):
                 self.searchDeltaX = -self.searchDeltaX
            self.yaw_servo.adjust_angle(self.searchDeltaX)

            self.pitch_servo.set_angle(15)

    def track(self):
        if not self.target_found:
            self.set_state(TurretState.SEARCHING)
            return

        self.aim()

        if self.is_locked():
            self.set_state(TurretState.LOCKED)

    def lock(self):
        if not self.is_locked():
            if self.target_found:
                self.set_state(TurretState.TRACKING)
            else:
                self.aim_point = (-1, -1)
                self.set_state(TurretState.SEARCHING)
            return
        
        self.aim()
        
        if self.locked_time is None:
            self.locked_time = time.time()
        elif time.time() - self.locked_time > 1.5 and self.armed:
            self.set_state(TurretState.FIRING)
        if not self.target_found:
            self.set_state(TurretState.SEARCHING)

    def fire_turret(self):
        if self.armed:
            self.fire_servo.max()
            sleep(0.22)
            self.fire_servo.mid()
            self.target = self.target + 1
            self.set_state(TurretState.SEARCHING)

    def is_locked(self):
        aim_x, aim_y = self.aim_point
        return ((640/2)-self.AIM_WINDOW_SIZE) < aim_x < ((640/2)+self.AIM_WINDOW_SIZE) and \
               ((480/2)-self.AIM_WINDOW_SIZE) < aim_y < ((480/2)+self.AIM_WINDOW_SIZE)

    def aim(self):
        aim_x, aim_y = self.aim_point
        # Use PID controllers to calculate adjustments
        yaw_adjustment = self.yaw_pid(aim_x)
        pitch_adjustment = self.pitch_pid(aim_y)
        print(yaw_adjustment * -1, pitch_adjustment)
        # Apply adjustments to servos
        self.yaw_servo.adjust_angle(yaw_adjustment * -1)
        self.pitch_servo.adjust_angle(pitch_adjustment)

    def update_aimpoint(self):
        # use keypoints to identify target aim point between the shoulders
        LEFT_SHOULDER = 5
        RIGHT_SHOULDER = 6
        if self.keypoints is not None and len(self.keypoints) > 0:
            if self.target >= len(self.keypoints):
                self.target = 0
            if self.scores[self.target] < 0.1:
                self.target = 0
            target_keypoints = self.keypoints[self.target]
            if target_keypoints[LEFT_SHOULDER][2] > 0.1 and target_keypoints[RIGHT_SHOULDER][2] > 0.1:
                # Calculate aim point between shoulders
                aimPointX = int((target_keypoints[LEFT_SHOULDER][0] + target_keypoints[RIGHT_SHOULDER][0]) / 2)
                aimPointY = int((target_keypoints[LEFT_SHOULDER][1] + target_keypoints[RIGHT_SHOULDER][1]) / 2)
            else:
                # Use the keypoint with the highest confidence
                sorted_keypoints = sorted(
                    target_keypoints,
                    key=lambda kp: kp[2],
                    reverse=True
                )
                aimPointX = int(sorted_keypoints[0][0])
                aimPointY = int(sorted_keypoints[0][1])
            self.aim_point = (aimPointX, aimPointY)
        else:
            self.aim_point = (-1, -1)

