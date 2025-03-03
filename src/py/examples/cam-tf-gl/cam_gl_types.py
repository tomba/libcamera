import libcamera as libcam

class MyBuf:
    idx: int
    cam: libcam.Camera
    stream: libcam.Stream
    buffer: libcam.FrameBuffer
    fd: int
