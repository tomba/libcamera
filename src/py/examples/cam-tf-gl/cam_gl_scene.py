ENABLE_TF = False

import os
import numpy as np

if ENABLE_TF:
    import tensorflow as tf

from cam_gl_yuyv_renderer import YUYV_Renderer
from cam_gl_downscaler import TextureDownscaler
from cam_gl_rect_renderer import RectangleRenderer
from cam_gl_text_renderer import TextRenderer
from cam_egl import EglSurface
from cam_gl_types import MyBuf

class GLScene:
    def __init__(self):
        self.width = 0
        self.height = 0

    def set_viewport(self, width, height):
        self.width = width
        self.height = height
        self.yuyv_renderer.set_viewport(width, height)

    def setup(self, egl_surface: EglSurface, mybufs):
        self.egl_surface = egl_surface

        self.yuyv_renderer = YUYV_Renderer(egl_surface.egl.display, mybufs)

        self.rect_renderer = RectangleRenderer()

        script_dir = os.path.dirname(os.path.abspath(__file__))

        atlas_path = script_dir + '/font_atlas.png'
        self.text_renderer = TextRenderer(atlas_path)

        sconfig = mybufs[0].stream.configuration

        # We can set the viewports here as they are fixed to the input size
        self.rect_renderer.set_viewport(sconfig.size.width, sconfig.size.height)
        self.text_renderer.set_viewport(sconfig.size.width, sconfig.size.height)

        downscaler_width = 300
        downscaler_height = 300

        self.downscaler = TextureDownscaler()
        self.downscaler.setup(sconfig.size.width, sconfig.size.height, downscaler_width, downscaler_height)
        # preallocate the downscale target buffer
        self.downscale_buf = np.zeros((downscaler_height, downscaler_width, 4), dtype=np.uint8)

        if ENABLE_TF:
            self.setup_tf()

    def setup_tf(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # TF
        # Read and parse the labels to a dict

        with open(script_dir + "/coco_labels.txt", 'r') as f:
            lines = f.readlines()

        kvps = [line.strip().split(maxsplit=1) for line in lines]
        kvps = [[int(kvp[0]), kvp[1]] for kvp in kvps]
        LABELS = dict(kvps)

        # Set up the interpreter

        interpreter = tf.lite.Interpreter(model_path=str(script_dir + "/mobilenet_v2.tflite"))
        interpreter.allocate_tensors()

        self.tf_data = {
            'labels': LABELS,
            'interpreter': interpreter,
        }

    def render(self, mybuf):
        self.downscale(mybuf)

        # XXX Apparently we can't ret RGB from the GPU, so we
        # have to drop the A here.
        rgb_array = self.downscale_buf[:, :, 0:3]
        rgb_array[:, :, [0, 2]] = rgb_array[:, :, [2, 0]]

        sconfig = mybuf.stream.configuration

        if ENABLE_TF:
            boxes = InferenceTensorFlow(rgb_array, self.tf_data, sconfig.size.width, sconfig.size.height)
            #print(boxes)
        else:
            boxes = [
                ((0, 0), (200, 200), "Test1"),
                ((300, 100), (500, 400), "Test2"),
            ]

        self.yuyv_renderer.draw(mybuf.idx)

        rectangles = [trip[0:2] for trip in boxes]

        #rectangles = [
        #    ((0, 0), (640*2-10, 100)),
        #    #((150, 50), (250, 200))
        #]
        self.rect_renderer.render(rectangles)

        texts = [(trip[2], trip[0][0], trip[0][1]) for trip in boxes]

#        texts = [
#            ("Label 1", 100, 80),          # Default scale (1.0)
#            ("Label 2", 300, 130, 1.5),    # Larger scale (1.5)
#            ("Small text", 200, 250, 0.8)  # Smaller scale (0.8)
#        ]

        self.text_renderer.render_texts(texts)

    def downscale(self, mybuf: MyBuf):
        self.downscaler.downscale(mybuf.buffer.planes[0].fd,
                                           dst_data=self.downscale_buf)

        #from PIL import Image
        #im = Image.fromarray(self.downscale_buf)
        #im.save("downscaled.png")

def InferenceTensorFlow(image, tf_data, scale_width, scale_height):
    labels = tf_data['labels']
    interpreter = tf_data['interpreter']

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    height = input_details[0]['shape'][1]
    width = input_details[0]['shape'][2]
    floating_model = False
    if input_details[0]['dtype'] == np.float32:
        floating_model = True

    assert image.shape[0] == height
    assert image.shape[1] == width

    picture = image

    input_data = np.expand_dims(picture, axis=0)
    if floating_model:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]['index'], input_data)

    interpreter.invoke()

    detected_boxes = interpreter.get_tensor(output_details[0]['index'])
    detected_classes = interpreter.get_tensor(output_details[1]['index'])
    detected_scores = interpreter.get_tensor(output_details[2]['index'])
    num_boxes = interpreter.get_tensor(output_details[3]['index'])

    boxes = []
    for i in range(int(num_boxes[0])):
        top, left, bottom, right = detected_boxes[0][i]
        classId = int(detected_classes[0][i])
        score = detected_scores[0][i]
        if score > 0.5:
            x1 = int(left * scale_width)
            y1 = int(top * scale_height)
            x2 = int(right * scale_width)
            y2 = int(bottom * scale_height)

            boxes.append(((x1, y1), (x2, y2), labels[classId]))

            #print(labels[classId], 'score = ', score)

#            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0, 0))
#
#            font = cv2.FONT_HERSHEY_SIMPLEX
#            cv2.putText(image, labels[classId], (x1 + 10, y1 + 10), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

    return boxes

