#!/usr/bin/python3

# Mostly copied from https://picamera.readthedocs.io/en/release-1.13/recipes2.html
# Run this script, then point a web browser at http:<this-ip-address>:8000
# Note: needs simplejpeg to be installed (pip3 install simplejpeg).

import io
import logging
import socketserver
from http import server
from threading import Condition
from http.server import SimpleHTTPRequestHandler
import os
from urllib.parse import urlparse, parse_qs  # Add this import

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

PAGE = """\
<html>
<head>
<title>Turret Stream</title>
</head>
<body>
<h1>Turret View</h1>
<img src="stream.mjpg" />
<button id="armDisarmButton">Arm</button>
<script src="script.js"></script>
</body>
</html>
"""

# Turret State
armed_state = False
mode = 'search'

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.output = kwargs.pop('output', None)
        super().__init__(*args, directory='static', **kwargs)

    def do_GET(self):
        global armed_state
        parsed_url = urlparse(self.path)  # Parse the URL
        path = parsed_url.path  # Extract the path
        query_params = parse_qs(parsed_url.query)  # Extract query parameters as a dictionary

        if path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with self.output.condition:
                        self.output.condition.wait()
                        frame = self.output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        elif path == '/set_armed':
            armed_state = query_params.get('armed', ['false'])[0].lower() == 'true'
            self.send_response(200)
            self.end_headers()
        else:
            super().do_GET()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    
server = None
def start_streaming_server(output, address=('', 8000)):
    global server
    server = StreamingServer(address, lambda *args, **kwargs: StreamingHandler(*args, output=output, **kwargs))
    print(f"Starting server at {server.server_address}")
    server.serve_forever()
def stop_streaming_server():
    global server
    if server:
        server.shutdown()
        server.server_close()
        server = None
        print("Server stopped.")
    else:
        print("No server to stop.")
        
if __name__ == "__main__":
    with Picamera2() as picam2:
        picam2.configure(picam2.create_video_configuration())
        output = StreamingOutput()
        picam2.start_recording(JpegEncoder(), FileOutput(output))

        try:
            start_streaming_server(output)
        finally:
            picam2.stop_recording()