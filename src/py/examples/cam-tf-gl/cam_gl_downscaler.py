import os
import numpy as np
import ctypes
from OpenGL import GL as gl
import OpenGL.EGL as egl

from dmabuf_utils import dmabuf_importer
from OpenGL.GLES2.OES.EGL_image_external import GL_TEXTURE_EXTERNAL_OES

class TextureDownscaler:
    def __init__(self):
        self.program = None
        self.vbo = None
        self.ibo = None
        self.fbo = None
        self.src_texture = None
        self.dst_texture = None
        self.position_loc = None
        self.texcoord_loc = None
        self.texture_loc = None
        self.src_width = 0
        self.src_height = 0
        self.dst_width = 0
        self.dst_height = 0
        self.initialized = False
        self.egl_image = None

    def setup(self, src_width, src_height, dst_width, dst_height):
        self.src_width = src_width
        self.src_height = src_height
        self.dst_width = dst_width
        self.dst_height = dst_height

        if egl.eglGetCurrentContext() == egl.EGL_NO_CONTEXT:
            return False

        self.program = self._create_shader_program()
        if not self.program:
            return False

        self.position_loc = gl.glGetAttribLocation(self.program, 'a_position')
        self.texcoord_loc = gl.glGetAttribLocation(self.program, 'a_texCoord')
        self.texture_loc = gl.glGetUniformLocation(self.program, 'u_texture')

        if not self._setup_buffers():
            self.cleanup()
            return False

        if not self._setup_textures():
            self.cleanup()
            return False

        if not self._setup_fbo():
            self.cleanup()
            return False

        self.initialized = True
        return True

    def _create_shader_program(self):
        from OpenGL.GLES2 import shaders

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

        void main() {
            gl_FragColor = texture2D(u_texture, vec2(1.0 - v_texCoord.x, v_texCoord.y));
        }
        '''

        try:
            vertex = shaders.compileShader(vertex_shader, gl.GL_VERTEX_SHADER)
            fragment = shaders.compileShader(fragment_shader, gl.GL_FRAGMENT_SHADER)
            program = shaders.compileProgram(vertex, fragment)
            return program
        except Exception:
            return None

    def _setup_buffers(self):
        try:
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
        except Exception:
            return False

    def _setup_textures(self):
        try:
            self.src_texture = gl.glGenTextures(1)
            gl.glBindTexture(GL_TEXTURE_EXTERNAL_OES, self.src_texture)
            gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

            self.dst_texture = gl.glGenTextures(1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.dst_texture)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, self.dst_width, self.dst_height, 0,
                          gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)

            return True
        except Exception:
            return False

    def _setup_fbo(self):
        try:
            self.fbo = gl.glGenFramebuffers(1)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0,
                                    gl.GL_TEXTURE_2D, self.dst_texture, 0)

            status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            if status != gl.GL_FRAMEBUFFER_COMPLETE:
                return False

            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
            return True
        except Exception:
            return False

    def downscale(self, dmabuf_fd, dst_data):
        # Using our utility to import the dmabuf
        egl_display = egl.eglGetCurrentDisplay()

        # First clean up any previous EGL image if it exists
        if self.egl_image:
            dmabuf_importer.destroy_image(egl_display, egl_image=self.egl_image)

        # Import new dmabuf
        self.egl_image = dmabuf_importer.import_dmabuf(
            egl_display, self.src_texture, dmabuf_fd,
            self.src_width, self.src_height
        )

        if not self.egl_image:
            return False

        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
        gl.glViewport(0, 0, self.dst_width, self.dst_height)
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
        gl.glBindTexture(GL_TEXTURE_EXTERNAL_OES, self.src_texture)
        gl.glUniform1i(self.texture_loc, 0)

        gl.glDrawElements(gl.GL_TRIANGLES, 6, gl.GL_UNSIGNED_SHORT, None)


        gl.glReadPixels(0, 0, self.dst_width, self.dst_height,
                        gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, dst_data)

        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
