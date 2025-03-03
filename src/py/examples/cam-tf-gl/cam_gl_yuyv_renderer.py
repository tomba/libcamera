import numpy as np
import ctypes
from OpenGL import GL as gl
from OpenGL.GLES2 import shaders

from dmabuf_utils import dmabuf_importer
from OpenGL.GLES2.OES.EGL_image_external import GL_TEXTURE_EXTERNAL_OES

class YUYV_Renderer:
    def __init__(self, display, input_buffers):
        self.egl_display = display
        self.input_buffers = input_buffers

        sconfig = input_buffers[0].stream.configuration

        self.buf_width = sconfig.size.width
        self.buf_height = sconfig.size.height

        self.input_textures = {}
        self.width = 0
        self.height = 0
        self.program = None
        self.vbo = None
        self.ibo = None
        self.position_loc = None
        self.texcoord_loc = None
        self.y_texture_loc = None
        self.initialized = False

        self._init_gl()

    def _init_gl(self):
        self.program = self._create_shader_program()
        assert self.program

        gl.glUseProgram(self.program)

        self.position_loc = gl.glGetAttribLocation(self.program, 'a_position')
        self.texcoord_loc = gl.glGetAttribLocation(self.program, 'a_texCoord')
        self.y_texture_loc = gl.glGetUniformLocation(self.program, 'u_texture')

        texture_size_loc = gl.glGetUniformLocation(self.program, 'texture_size')
        gl.glUniform2f(texture_size_loc, float(self.buf_width), float(self.buf_height))

        self._setup_buffers()
        self._setup_input_textures()

        self.initialized = True
        return True

    def _create_shader_program(self):
        vertex_shader = '''
        attribute vec2 a_position;
        attribute vec2 a_texCoord;
        varying vec2 v_texCoord;

        void main() {
            gl_Position = vec4(a_position, 0.0, 1.0);
            v_texCoord = a_texCoord;
        }
        '''

        fragment_shader = '''
        #extension GL_OES_EGL_image_external : enable
        precision mediump float;
        varying vec2 v_texCoord;
        uniform samplerExternalOES u_texture;
        uniform vec2 texture_size;

        void main() {
            gl_FragColor = texture2D(u_texture, 1.0 - v_texCoord);
        }
        '''

        vertex = shaders.compileShader(vertex_shader, gl.GL_VERTEX_SHADER)
        fragment = shaders.compileShader(fragment_shader, gl.GL_FRAGMENT_SHADER)

        if gl.glGetShaderiv(fragment, gl.GL_COMPILE_STATUS) != gl.GL_TRUE:
            error_log = gl.glGetShaderInfoLog(fragment).decode()
            raise RuntimeError(f'shader compilation failed:\n{error_log}')

        program = shaders.compileProgram(vertex, fragment)

        if gl.glGetProgramiv(program, gl.GL_LINK_STATUS) != gl.GL_TRUE:
            error_log = gl.glGetProgramInfoLog(program).decode()
            raise RuntimeError(f'Shader program linking failed:\n{error_log}')

        return program

    def _setup_buffers(self):
        vertices = np.array([
            -1.0, -1.0,   0.0, 0.0,
             1.0, -1.0,   1.0, 0.0,
            -1.0,  1.0,   0.0, 1.0,
             1.0,  1.0,   1.0, 1.0,
        ], dtype=np.float32)

        indices = np.array([
            0, 1, 2,
            2, 1, 3
        ], dtype=np.uint16)

        self.vbo = gl.glGenBuffers(1)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STATIC_DRAW)

        self.ibo = gl.glGenBuffers(1)
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self.ibo)
        gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, gl.GL_STATIC_DRAW)

        return True

    def _setup_input_textures(self):
        for buffer in self.input_buffers:
            buffer_id = buffer.idx
            dmabuf_fd = buffer.fd

            # Use the utility to create textures from dmabufs
            texture_id, _ = dmabuf_importer.create_texture_from_dmabuf(
                self.egl_display,
                dmabuf_fd,
                self.buf_width,
                self.buf_height,
                buffer_id=buffer_id
            )

            if texture_id:
                self.input_textures[buffer_id] = texture_id

    def set_viewport(self, width: int, height: int):
        self.width = width
        self.height = height
        gl.glViewport(0, 0, width, height)

    def draw(self, buffer_id):
        assert self.initialized
        assert buffer_id in self.input_textures, f'Buffer {buffer_id} not found'

        gl.glViewport(0, 0, self.width, self.height)

        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        gl.glUseProgram(self.program)

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self.ibo)

        stride = 4 * 4

        gl.glEnableVertexAttribArray(self.position_loc)
        gl.glVertexAttribPointer(self.position_loc, 2, gl.GL_FLOAT, gl.GL_FALSE,
                             stride, ctypes.c_void_p(0))

        gl.glEnableVertexAttribArray(self.texcoord_loc)
        gl.glVertexAttribPointer(self.texcoord_loc, 2, gl.GL_FLOAT, gl.GL_FALSE,
                             stride, ctypes.c_void_p(8))

        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(GL_TEXTURE_EXTERNAL_OES, self.input_textures[buffer_id])
        gl.glUniform1i(self.y_texture_loc, 0)

        gl.glDrawElements(gl.GL_TRIANGLES, 6, gl.GL_UNSIGNED_SHORT, None)
