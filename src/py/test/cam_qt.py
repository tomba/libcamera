from PyQt5 import QtCore, QtGui, QtWidgets
from io import BytesIO
from PIL import Image
from PIL.ImageQt import ImageQt
import numpy as np
import sys

def rgb_to_pix(rgb):
	img = Image.frombuffer("RGB", (rgb.shape[1], rgb.shape[0]), rgb)
	qim = ImageQt(img).copy()
	pix = QtGui.QPixmap.fromImage(qim)
	return pix

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
			w, h = cfg.size
			pitch = cfg.stride

			if cfg.fmt == "MJPEG":
				img = Image.open(BytesIO(b))
				qim = ImageQt(img).copy()
				pix = QtGui.QPixmap.fromImage(qim)
			elif cfg.fmt == "YUYV":
				# YUV422
				yuyv = np.array(b, dtype=np.uint8).reshape((h, w // 2 * 4))

				# YUV444
				yuv = np.empty((h, w, 3), dtype=np.uint8)
				yuv[:, :, 0] = yuyv[:, 0::2]					# Y
				yuv[:, :, 1] = yuyv[:, 1::4].repeat(2, axis=1)	# U
				yuv[:, :, 2] = yuyv[:, 3::4].repeat(2, axis=1)	# V

				m = np.array([
					[ 1.0, 1.0, 1.0],
					[-0.000007154783816076815, -0.3441331386566162, 1.7720025777816772],
					[ 1.4019975662231445, -0.7141380310058594 , 0.00001542569043522235]
				])

				rgb = np.dot(yuv, m)
				rgb[:, :, 0] -= 179.45477266423404
				rgb[:, :, 1] += 135.45870971679688
				rgb[:, :, 2] -= 226.8183044444304
				rgb = rgb.astype(np.uint8)

				pix = rgb_to_pix(rgb)
			elif cfg.fmt == "RGB888":
				rgb = np.array(b, dtype=np.uint8).reshape((h, w, 3))

				pix = rgb_to_pix(rgb)
			elif cfg.fmt in ["ARGB8888", "XRGB8888"]:
				rgb = np.array(b, dtype=np.uint8).reshape((h, w, 4))
				# drop alpha component
				rgb = np.delete(rgb, np.s_[3::4], axis=2)

				pix = rgb_to_pix(rgb)
			else:
				raise Exception("Format not supported: " + cfg.fmt)

		return pix

	def handle_request(self, stream, fb):
		ctx = self.ctx

		pix = self.buf_to_qpixmap(stream, fb)
		self.label.setPixmap(pix)

		self.frameLabel.setText("Queued: {}\nDone: {}\nFps: {:.2f}"
        	.format(ctx["reqs-queued"], ctx["reqs-completed"], ctx["fps"]))
