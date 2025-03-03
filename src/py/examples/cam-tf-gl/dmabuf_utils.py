import ctypes
from OpenGL import GL as gl
import OpenGL.EGL as egl
from OpenGL.EGL.EXT import image_dma_buf_import as ext_dmabuf
from OpenGL.EGL.KHR.image import EGLImageKHR, eglCreateImageKHR, eglDestroyImageKHR
from OpenGL.raw.GLES2 import _types as _cs
from OpenGL.platform import PLATFORM
from OpenGL.GLES2.OES.EGL_image_external import GL_TEXTURE_EXTERNAL_OES

import pixutils.formats

class DMABufImporter:
    def __init__(self):
        self._setup_extension_procs()
        self._egl_images = {}

    def _setup_extension_procs(self):
        self.glEGLImageTargetTexture2DOES = ctypes.CFUNCTYPE(
            None,
            _cs.GLenum,
            _cs.GLeglImageOES,
        )(PLATFORM.getExtensionProcedure(b'glEGLImageTargetTexture2DOES'))

    def import_dmabuf(self, egl_display, texture_id, dmabuf_fd, width, height,
                     pixel_format=None, buffer_id=None):
        """
        Import a DMABuf as an OpenGL texture using EGLImage.

        Args:
            egl_display: EGL display
            texture_id: GL texture ID to bind the image to
            dmabuf_fd: DMABuf file descriptor
            width: Buffer width
            height: Buffer height
            pixel_format: Optional pixel format (defaults to YUYV)
            buffer_id: Optional buffer ID for tracking

        Returns:
            EGLImage handle or None on failure
        """
        #if pixel_format is None:
        pixel_format = pixutils.formats.PixelFormats.YUYV

        attribs = [
            egl.EGL_WIDTH, width,
            egl.EGL_HEIGHT, height,
            ext_dmabuf.EGL_LINUX_DRM_FOURCC_EXT, pixel_format.drm_fourcc,
            ext_dmabuf.EGL_DMA_BUF_PLANE0_FD_EXT, dmabuf_fd,
            ext_dmabuf.EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
            ext_dmabuf.EGL_DMA_BUF_PLANE0_PITCH_EXT, pixel_format.stride(width, 0),
            ext_dmabuf.EGL_YUV_COLOR_SPACE_HINT_EXT, ext_dmabuf.EGL_ITU_REC601_EXT,
            ext_dmabuf.EGL_SAMPLE_RANGE_HINT_EXT, ext_dmabuf.EGL_YUV_NARROW_RANGE_EXT,
            egl.EGL_NONE
        ]

        egl_image = eglCreateImageKHR(egl_display, egl.EGL_NO_CONTEXT,
                                     ext_dmabuf.EGL_LINUX_DMA_BUF_EXT, None, attribs)

        if not egl_image:
            return None

        gl.glBindTexture(GL_TEXTURE_EXTERNAL_OES, texture_id)
        self.glEGLImageTargetTexture2DOES(GL_TEXTURE_EXTERNAL_OES, egl_image)

        if buffer_id is not None:
            self._egl_images[buffer_id] = egl_image

        return egl_image

    def create_texture_from_dmabuf(self, egl_display, dmabuf_fd, width, height,
                                 pixel_format=None, buffer_id=None):
        """
        Create a new texture and import a DMABuf into it.

        Args:
            egl_display: EGL display
            dmabuf_fd: DMABuf file descriptor
            width: Buffer width
            height: Buffer height
            pixel_format: Optional pixel format (defaults to YUYV)
            buffer_id: Optional buffer ID for tracking

        Returns:
            Tuple of (texture_id, egl_image) or (None, None) on failure
        """
        texture_id = gl.glGenTextures(1)
        gl.glBindTexture(GL_TEXTURE_EXTERNAL_OES, texture_id)
        gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(GL_TEXTURE_EXTERNAL_OES, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

        egl_image = self.import_dmabuf(egl_display, texture_id, dmabuf_fd,
                                      width, height, pixel_format, buffer_id)

        if egl_image is None:
            gl.glDeleteTextures(1, [texture_id])
            return None, None

        return texture_id, egl_image

    def destroy_image(self, egl_display, buffer_id=None, egl_image=None):
        """
        Destroy an EGLImage.

        Args:
            egl_display: EGL display
            buffer_id: Buffer ID to destroy
            egl_image: Specific EGLImage to destroy (if buffer_id not provided)
        """
        if buffer_id is not None and buffer_id in self._egl_images:
            eglDestroyImageKHR(egl_display, self._egl_images[buffer_id])
            del self._egl_images[buffer_id]
        elif egl_image is not None:
            eglDestroyImageKHR(egl_display, egl_image)

    def cleanup(self, egl_display):
        """
        Destroy all tracked EGLImages.

        Args:
            egl_display: EGL display
        """
        for buffer_id, egl_image in self._egl_images.items():
            eglDestroyImageKHR(egl_display, egl_image)
        self._egl_images.clear()


# Singleton instance for convenience
dmabuf_importer = DMABufImporter()
