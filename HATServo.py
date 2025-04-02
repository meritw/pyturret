import time
import PCA9685

"""
This class provides a simple interface to control a servo motor using the PWM Hat on a Raspberry Pi.
The PWM Hat connects with I2C and has a PCA9685 chip that allows for 16 channels of PWM output.
"""

pwm = PCA9685.PCA9685(0x40, debug=False)
pwm.setPWMFreq(50)  # Set frequency to 50Hz for servos

class HATServo:
    def __init__(self, channel, min_pulse=500, max_pulse=2500):
        """
        Initializes the HWServo object.

        :param pwm_chip: PWM chip number (default: 0)
        :param pwm_channel: PWM channel number (default: 0)
        :param min_duty: Minimum duty cycle in nanoseconds (default: 1000000 for 1ms pulse)
        :param max_duty: Maximum duty cycle in nanoseconds (default: 2000000 for 2ms pulse)
        :param frequency: PWM frequency in Hz (default: 50Hz for servos)
        """
        self.channel = channel
        self.min_pulse = min_pulse
        self.max_pulse = max_pulse
        self.current_angle = 0

        # Set the initial position to the middle of the range
        self.set_angle(0)

    def set_angle(self, angle):
        """
        Moves the servo to the specified angle.

        :param angle: Desired servo angle in degrees (-90 to 90)
        """
        self.current_angle = max(-90, min(90, angle))
        pwm.setServoPulse(self.channel, self._angle_to_pulse(self.current_angle))

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

    def disable(self):
        """ Disables the PWM output. """
        pwm.setPWM(self.channel, 0, 0)  # Set duty cycle to 0

    def cleanup(self):
        """ Disables and unexports the PWM channel. """
        self.disable()

    def get_angle(self):
        """ Returns the current angle of the servo. """
        return self.current_angle
    
    def _angle_to_pulse(self, angle):
        """
        Converts an angle in degrees to a pulse width in microseconds.

        :param
        angle: Angle in degrees (-90 to 90)
        :return: Pulse width in microseconds
        """ 
        # Map angle to pulse width
        pulse_width = self.min_pulse + (self.max_pulse - self.min_pulse) * (angle + 90) / 180
        return int(pulse_width)

# Example usage
if __name__ == "__main__":

    yawServo = HATServo(channel=0)
    # yawServo =   HWServo(pwm_chip=2, pwm_channel=1, min_duty=500000,  max_duty=2500000)
    # fireServo =  HWServo(pwm_chip=2, pwm_channel=0, min_duty=1000000,  max_duty=2000000)
    
    print("Moving to mid position...")
    yawServo.mid()
    # pitchServo.mid()
    # fireServo.mid()
    time.sleep(3)

    print("Incrementing angle by 30 degrees...")
    yawServo.adjust_angle(30)
    # pitchServo.adjust_angle(30)
    time.sleep(3)

    print("Decrementing angle by 60 degrees...")
    yawServo.adjust_angle(-60)
    # pitchServo.adjust_angle(-60)
    # fireServo.adjust_angle(-60)
    time.sleep(3)

    print("Disabling servos...")
    yawServo.cleanup()
    # pitchServo.cleanup()
    # fireServo.cleanup()
