import time
import os
import RPi.GPIO as GPIO

class HWServo:
    def __init__(self, pwm_chip=0, pwm_channel=0, min_duty=1000000, max_duty=2000000, frequency=50):
        """
        Initializes the HWServo object.

        :param pwm_chip: PWM chip number (default: 0)
        :param pwm_channel: PWM channel number (default: 0)
        :param min_duty: Minimum duty cycle in nanoseconds (default: 1000000 for 1ms pulse)
        :param max_duty: Maximum duty cycle in nanoseconds (default: 2000000 for 2ms pulse)
        :param frequency: PWM frequency in Hz (default: 50Hz for servos)
        """
        self.pwm_chip = pwm_chip
        self.pwm_channel = pwm_channel
        self.min_duty = min_duty
        self.max_duty = max_duty
        self.period = int(1e9 / frequency)  # Convert Hz to nanoseconds
        self.current_angle = 0  # Initialize current angle to 0

        self.pwm_path = f"/sys/class/pwm/pwmchip{self.pwm_chip}/pwm{self.pwm_channel}"

        self._enable_pwm()

    def _write_pwm(self, filename, value):
        """ Writes a value to a PWM sysfs file. """
        with open(os.path.join(self.pwm_path, filename), 'w') as f:
            f.write(str(value))

    def _enable_pwm(self):
        """ Exports and enables the PWM channel if not already enabled. """
        if not os.path.exists(self.pwm_path):
            with open(f"/sys/class/pwm/pwmchip{self.pwm_chip}/export", 'w') as f:
                f.write(str(self.pwm_channel))

        time.sleep(0.1)  # Allow time for system to create PWM interface

        self._write_pwm("period", self.period)
        self._write_pwm("enable", 1)

    def set_angle(self, angle):
        """
        Moves the servo to the specified angle.

        :param angle: Desired servo angle in degrees (typically -90 to 90 or 0 to 180)
        """
        if(angle >= -90 and angle <= 90):
            duty_cycle = self._angle_to_duty(angle)
            self._write_pwm("duty_cycle", duty_cycle)
            self.current_angle = angle  # Update current angle
        else:
            print(f"Angle out of range: {angle}")

    def adjust_angle(self, increment):
        """ Increments the current angle by the specified amount. """
        new_angle = self.current_angle + increment
        # clamp new_angle to -90 to 90
        new_angle = max(-90, min(90, new_angle))
        self.set_angle(new_angle)

    def min(self):
        """ Moves the servo to its minimum position (-90 degrees). """
        self.set_angle(-90)

    def mid(self):
        """ Moves the servo to its center position (0 degrees). """
        self.set_angle(0)

    def max(self):
        """ Moves the servo to its maximum position (90 degrees). """
        self.set_angle(90)

    def _angle_to_duty(self, angle):
        """ Converts an angle to the appropriate duty cycle. """
        angle = max(-90, min(90, angle))  # Clamp angle to safe range
        duty_cycle = self.min_duty + (angle + 90) * (self.max_duty - self.min_duty) / 180
        return int(duty_cycle)

    def disable(self):
        """ Disables the PWM output. """
        self._write_pwm("enable", 0)

    def cleanup(self):
        """ Disables and unexports the PWM channel. """
        self.disable()
        with open(f"/sys/class/pwm/pwmchip{self.pwm_chip}/unexport", 'w') as f:
            f.write(str(self.pwm_channel))

# Example usage
if __name__ == "__main__":

    pitchServo = HWServo(pwm_chip=2, pwm_channel=2, min_duty=1000000, max_duty=2000000)
    yawServo =   HWServo(pwm_chip=2, pwm_channel=1, min_duty=500000,  max_duty=2500000)
    fireServo =  HWServo(pwm_chip=2, pwm_channel=0, min_duty=1000000,  max_duty=2000000)
    
    print("Moving to mid position...")
    yawServo.mid()
    pitchServo.mid()
    fireServo.mid()
    time.sleep(3)

    print("Incrementing angle by 30 degrees...")
    yawServo.adjust_angle(30)
    pitchServo.adjust_angle(30)
    time.sleep(3)

    print("Decrementing angle by 60 degrees...")
    yawServo.adjust_angle(-60)
    pitchServo.adjust_angle(-60)
    fireServo.adjust_angle(-60)
    time.sleep(3)

    print("Disabling servos...")
    yawServo.mid()
    pitchServo.mid()
    time.sleep(1)
    yawServo.cleanup()
    pitchServo.cleanup()
    fireServo.cleanup()
