# pyturret

This is a python app to turn a [HackPack Turret](https://www.crunchlabs.com/products/ir-turret) into an AI powered sentry gun.

This runs on a Raspberry pi and uses the [AI Camera](https://www.raspberrypi.com/products/ai-camera/) to search for, track and fire at human-shaped targets.  It can track multiple targets and fire on them in sequence (sometimes).

The python application hosts a simple web page with a video stream of what the turret is seeing, overlayed with target information and basic info about the turret's state.  Simple controls are available on the web page to arm and disarm the turret (others, like manual control, could be added).
[screenshot of the web interface](images/screenshot.jpg)

Most of the heavy lifting is done by the AI Processor on the IMX500, so the CPU load on the pi ends up being quite small.

## Hardware:
You can use the Raspberry PI's built-in hardware PWN to control the servos or pick up a PWM Hat. The PWM Hat makes wiring easier and simplifies the software setup.  To use the pi's pwm directly you will definitely need to use hardware PWM, software will cause all kinds of jitter in the servos.  The pi 5 has 4 hardware PWM channels available so it will work, earlier models may have less.

I just removed the stock Arduino and plastic holder-thingy and stuck the pi down with some double-sided foam tape.  The camera is attached to the front of the turret with a rubber band and the ribbon cable is threaded under the main body to the pi.

[picture of the raspberry pi taped to the turret](images/setup.jpg)
[picture of the camera](images/camera.jpg)


## Software:
### Installation
This should be pretty straightforward to get running on a raspberry pi with recent OS.  You'll need to install the camera software from Raspberry Pi and then create a python virtual environment to run the code.

NOTE: The venv must include raspberry pi system packages in order for picamera2 to work correctly.
```
python3 -m venv venv --system-site-packages
source venv/bin/activate`
pip install -r requirements.txt
```

### Usage
Run `python3 main.py` and the turret will start.  Some info is logged to the terminal and a web server is started on port 8000 of your raspberry pi.  If you named your pi "turret" when you burned the SD card you can probably access it at http://turret.local:8000/

Note: I really like to use Visual Studio Code's remote SSH workspace feature to work on this project.  Just point it at the folder on your pi and you get a really nice development environment where you can run the code in a debugger to see what's going on, run terminal commands, etc.  And you can run VS Code locally on your desktop so everything feels snappy (as opposed to running it on the pi which usually lags pretty badly).
