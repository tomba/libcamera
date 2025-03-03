from OpenGL import GL as gl
import numpy as np
from OpenGL.GLES2 import shaders

class RectangleRenderer:
    def __init__(self, line_width=1.0, color=(1.0, 1.0, 1.0, 1.0)):
        self.line_width = line_width
        self.color = color
        self.shader = None
        self.vbo = None
        self.width = 0
        self.height = 0
        self.setup()

    def setup(self):
        vertex_src = '''
        attribute vec2 a_position;
        uniform vec2 u_resolution;

        void main() {
            // Convert from pixel coordinates to normalized device coordinates
            vec2 normalized = (a_position / u_resolution) * 2.0 - 1.0;
            // Flip y-coordinate as OpenGL has (0,0) at bottom-left
            normalized.y = -normalized.y;
            gl_Position = vec4(normalized, 0.0, 1.0);
        }
        '''

        fragment_src = '''
        precision mediump float;
        uniform vec4 u_color;

        void main() {
            gl_FragColor = u_color;
        }
        '''

        try:
            vertex = shaders.compileShader(vertex_src, gl.GL_VERTEX_SHADER)
            fragment = shaders.compileShader(fragment_src, gl.GL_FRAGMENT_SHADER)
            self.shader = shaders.compileProgram(vertex, fragment)
        except Exception as e:
            print(f'Failed to compile shaders: {e}')
            return False

        # Create VBO
        self.vbo = gl.glGenBuffers(1)
        return True

    def set_viewport(self, width, height):
        self.width = width
        self.height = height

    def render(self, rectangles):
        if not rectangles or not self.shader or self.width == 0 or self.height == 0:
            return

        # Use shader program
        gl.glUseProgram(self.shader)

        # Set color uniform
        color_loc = gl.glGetUniformLocation(self.shader, 'u_color')
        gl.glUniform4f(color_loc, *self.color)

        # Set resolution uniform
        resolution_loc = gl.glGetUniformLocation(self.shader, 'u_resolution')
        gl.glUniform2f(resolution_loc, float(self.width), float(self.height))

        # Set line width
        gl.glLineWidth(self.line_width)

        # Get attribute location
        position_loc = gl.glGetAttribLocation(self.shader, 'a_position')

        # Bind VBO
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        gl.glEnableVertexAttribArray(position_loc)
        gl.glVertexAttribPointer(position_loc, 2, gl.GL_FLOAT, gl.GL_FALSE, 0, None)

        for rect in rectangles:
            top_left = rect[0]
            bottom_right = rect[1]

            # Extract coordinates
            x1, y1 = top_left
            x2, y2 = bottom_right

            # Create vertex data for lines (8 vertices for 4 lines)
            vertices = np.array([
                # Top line
                x1, y1,
                x2, y1,
                # Right line
                x2, y1,
                x2, y2,
                # Bottom line
                x2, y2,
                x1, y2,
                # Left line
                x1, y2,
                x1, y1
            ], dtype=np.float32)

            # Upload data to GPU
            gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STREAM_DRAW)

            # Draw lines
            gl.glDrawArrays(gl.GL_LINES, 0, 8)

        # Clean up
        gl.glDisableVertexAttribArray(position_loc)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glUseProgram(0)
