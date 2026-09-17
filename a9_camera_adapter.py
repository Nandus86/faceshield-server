import cv2
import numpy as np
import io
import time
import threading
import sys
import os
from PIL import Image

# Setup path so it finds the library folder
sys.path.append(os.path.join(os.path.dirname(__file__), 'a9_camera_lib'))

from netcl_tcp import netcl_tcp
from v720_ap import v720_ap
import cmd_udp

class A9VideoCapture:
    def __init__(self, host="192.168.169.1", port=6123):
        self.host = host
        self.port = port
        self.is_opened = False
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.thread = None
        self.running = False
        self.sock = None
        
        self._start_capture()
        
    def _start_capture(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        
        # Give it a moment to connect
        for _ in range(20):
            if self.is_opened:
                break
            time.sleep(0.1)
        
    def _capture_loop(self):
        try:
            with netcl_tcp(self.host, self.port) as sock:
                self.sock = sock
                cam = v720_ap(sock)
                try:
                    cam.init_live_motion()
                    self.is_opened = True
                    print("A9 Camera Connected Successfully")
                except Exception as e:
                    print(f"Failed to connect to A9 Camera: {e}")
                    self.is_opened = False
                    self.running = False
                    return

                sync = False
                frame_buffer = bytearray()

                def on_rcv(cmd, data: bytearray):
                    nonlocal sync, frame_buffer
                    
                    if not self.running:
                        raise KeyboardInterrupt("Stopping capture loop")
                        
                    if cmd == cmd_udp.P2P_UDP_CMD_JPEG:
                        if not sync:
                            f = data.find(b'\xff\xd8')
                            if f != -1:
                                frame_buffer.extend(data[f:])
                                sync = True
                        else:  # sync == true
                            f = data.find(b'\xff\xd9')
                            if f != -1:
                                frame_buffer.extend(data[:f+2])
                                
                                try:
                                    img = Image.open(io.BytesIO(frame_buffer))
                                    # Convert RGB to BGR for OpenCV
                                    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                                    
                                    with self.frame_lock:
                                        self.latest_frame = cv_img
                                except Exception as e:
                                    print(f"Error decoding frame: {e}")
                                    
                                frame_buffer.clear()
                                sync = False
                            else:
                                frame_buffer.extend(data)

                try:
                    cam.cap_live(on_rcv)
                except KeyboardInterrupt:
                    pass
                except Exception as e:
                    print(f"Video stream error: {e}")
        except Exception as e:
            print(f"A9 Camera Socket Error: {e}")
            
        self.is_opened = False
        self.running = False

    def isOpened(self):
        return self.is_opened
        
    def read(self):
        with self.frame_lock:
            if self.latest_frame is not None:
                return True, self.latest_frame.copy()
            else:
                return False, None
                
    def release(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.is_opened = False
