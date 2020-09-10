from PyQt5 import QtCore, QtGui, QtWidgets
from io import BytesIO
from PIL import Image
from PIL.ImageQt import ImageQt
import numpy as np
import sys

format_map = {
	"YUYV": QtGui.QImage.Format_RGB16,
	"MJPEG": QtGui.QImage.Format_RGB888,
	"BGR888": QtGui.QImage.Format_RGB888,
	"RGB888": QtGui.QImage.Format_RGB888,
	"ARGB8888": QtGui.QImage.Format_ARGB32,
	"XRGB8888": QtGui.QImage.Format_ARGB32, # XXX Format_RGB32 crashes?
}

class QtRenderer:
	def __init__(self, state):
		self.state = state

		self.cm = state["cm"]
		self.contexts = state["contexts"]

	def setup(self):
		self.app = QtWidgets.QApplication([])

		windows = []

		for ctx in self.contexts:
			camera = ctx["camera"]

			for stream in ctx["streams"]:
				fmt = stream.configuration.fmt
				size = stream.configuration.size

				if not fmt in format_map:
					raise Exception("Unsupported pixel format")

				window = MainWindow(ctx, stream)
				window.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
				window.show()
				windows.append(window)

		self.windows = windows

	def run(self):
		camnotif = QtCore.QSocketNotifier(self.cm.efd, QtCore.QSocketNotifier.Read)
		camnotif.activated.connect(lambda x: self.readcam())

		keynotif = QtCore.QSocketNotifier(sys.stdin.fileno(), QtCore.QSocketNotifier.Read)
		keynotif.activated.connect(lambda x: self.readkey())

		print("Capturing...")

		self.app.exec()

		print("Exiting...")

	def readcam(self):
		running = self.state["event_handler"](self.state)

		if not running:
			self.app.quit()

	def readkey(self):
		sys.stdin.readline()
		self.app.quit()

	def request_handler(self, ctx, req):
		buffers = req.buffers

		for stream, fb in buffers.items():
			wnd = next(wnd for wnd in self.windows if wnd.stream == stream)

			wnd.handle_request(stream, fb)

		self.state["request_prcessed"](ctx, req)

	def cleanup(self):
		for w in self.windows:
			w.close()


class MainWindow(QtWidgets.QWidget):
	def __init__(self, ctx, stream):
		super().__init__()

		self.ctx = ctx
		self.stream = stream

		self.label = QtWidgets.QLabel()

		windowLayout = QtWidgets.QHBoxLayout()
		self.setLayout(windowLayout)

		windowLayout.addWidget(self.label)

		controlsLayout = QtWidgets.QVBoxLayout()
		windowLayout.addLayout(controlsLayout)

		windowLayout.addStretch()

		group = QtWidgets.QGroupBox("Info")
		groupLayout = QtWidgets.QVBoxLayout()
		group.setLayout(groupLayout)
		controlsLayout.addWidget(group)

		lab = QtWidgets.QLabel(ctx["id"])
		groupLayout.addWidget(lab)

		self.frameLabel = QtWidgets.QLabel()
		groupLayout.addWidget(self.frameLabel)


		group = QtWidgets.QGroupBox("Properties")
		groupLayout = QtWidgets.QVBoxLayout()
		group.setLayout(groupLayout)
		controlsLayout.addWidget(group)

		camera = ctx["camera"]

		for k, v in camera.properties.items():
			lab = QtWidgets.QLabel()
			lab.setText(k + " = " + str(v))
			groupLayout.addWidget(lab)

		group = QtWidgets.QGroupBox("Controls")
		groupLayout = QtWidgets.QVBoxLayout()
		group.setLayout(groupLayout)
		controlsLayout.addWidget(group)

		for k, (min, max, default) in camera.controls.items():
			lab = QtWidgets.QLabel()
			lab.setText("{} = {}/{}/{}".format(k, min, max, default))
			groupLayout.addWidget(lab)

		controlsLayout.addStretch()

	def buf_to_qpixmap(self, stream, fb):
		with fb.mmap(0) as b:
			cfg = stream.configuration
			qfmt = format_map[cfg.fmt]
			w, h = cfg.size
			pitch = cfg.stride

			if cfg.fmt == "MJPEG":
				img = Image.open(BytesIO(b))
				qim = ImageQt(img).copy()
				pix = QtGui.QPixmap.fromImage(qim)
			elif cfg.fmt == "YUYV":
				arr = np.array(b)
				y = arr[0::2]
				u = arr[1::4]
				v = arr[3::4]

				yuv = np.ones((len(y)) * 3, dtype=np.uint8)
				yuv[::3] = y
				yuv[1::6] = u
				yuv[2::6] = v
				yuv[4::6] = u
				yuv[5::6] = v

				# XXX YCbCr doesn't work?
				#img = Image.frombytes("YCbCr", (w, h), yuv.tobytes())
				img = Image.frombuffer("RGB", (w, h), yuv)

				qim = ImageQt(img).copy()
				pix = QtGui.QPixmap.fromImage(qim)
			else:
				img = QtGui.QImage(b, w, h, pitch, qfmt)
				pix = QtGui.QPixmap.fromImage(img)

		return pix

	def handle_request(self, stream, fb):
		global format_map

		ctx = self.ctx

		pix = self.buf_to_qpixmap(stream, fb)
		self.label.setPixmap(pix)

		self.frameLabel.setText("Queued: {}\nDone: {}\nFps: {:.2f}"
        	.format(ctx["reqs-queued"], ctx["reqs-completed"], ctx["fps"]))
