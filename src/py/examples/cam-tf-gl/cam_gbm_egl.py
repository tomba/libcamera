from __future__ import annotations

import kms
from cam_egl import EglState, EglSurface
import gbm

class GbmEglSurface:
    # Class-level cache of buffer objects to framebuffers
    _fb_cache = {}

    def __init__(self, card, gbm_dev: gbm.GbmDevice, egl_state: EglState, width: int, height: int):
        self.card = card
        self.egl = egl_state
        self.width = width
        self.height = height

        self.gbm_surface = gbm_dev.create_surface(
            width,
            height,
            gbm.GBM_FORMAT_XRGB8888,
            gbm.GBM_BO_USE_SCANOUT | gbm.GBM_BO_USE_RENDERING
        )

        self.egl_surface = EglSurface(self.egl, self.gbm_surface.handle)

        self.bo_prev = None
        self.bo_next = None

    def make_current(self):
        if not self.gbm_surface.has_free_buffers:
            raise RuntimeError('No free buffers')
        self.egl_surface.make_current()

    def swap_buffers(self):
        self.egl_surface.swap_buffers()

    def _create_framebuffer(self, bo):
        return kms.ExtFramebuffer(
            self.card,
            bo.width,
            bo.height,
            kms.PixelFormats.XRGB8888,
            [bo.handle],
            [bo.stride],
            [0]
        )

    def _get_fb_for_bo(self, bo):
        if bo not in self._fb_cache:
            self._fb_cache[bo] = self._create_framebuffer(bo)
        return self._fb_cache[bo]

    def lock_next(self):
        self.bo_prev = self.bo_next
        self.bo_next = self.gbm_surface.lock_front_buffer()
        if not self.bo_next:
            raise RuntimeError('Could not lock GBM buffer')

        return self._get_fb_for_bo(self.bo_next)

    def free_prev(self):
        if self.bo_prev:
            if self.bo_prev in self._fb_cache:
                del self._fb_cache[self.bo_prev]
            self.gbm_surface.release_buffer(self.bo_prev)
            self.bo_prev = None

    def __del__(self):
        if self.bo_next:
            if self.bo_next in self._fb_cache:
                del self._fb_cache[self.bo_next]
            self.gbm_surface.release_buffer(self.bo_next)
