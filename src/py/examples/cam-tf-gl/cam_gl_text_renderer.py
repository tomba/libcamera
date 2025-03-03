from OpenGL import GL as gl
import numpy as np
from OpenGL.GLES2 import shaders
from PIL import Image

class TextRenderer:
    # Font atlas parameters - update these with values from font_atlas_generator.py
    FIRST_CHAR = 32  # ASCII code of first character (space)
    CELL_WIDTH = 16  # Width of each character cell
    CELL_HEIGHT = 20  # Height of each character cell
    CHARS_PER_ROW = 16  # Number of characters per row in atlas

    def __init__(self, atlas_path, color=(1.0, 1.0, 1.0, 1.0)):
        self.color = color
        self.shader = None
        self.vbo = None
        self.texture_id = None
        self.width = 0
        self.height = 0
        self.atlas_path = atlas_path
        self.atlas_width = 0
        self.atlas_height = 0
        self.setup()

    def setup(self):
        # Create shader program
        vertex_src = '''
        attribute vec2 a_position;
        attribute vec2 a_texCoord;
        uniform vec2 u_resolution;
        varying vec2 v_texCoord;

        void main() {
            // Convert from pixel coordinates to normalized device coordinates
            vec2 normalized = (a_position / u_resolution) * 2.0 - 1.0;
            // Flip y-coordinate as OpenGL has (0,0) at bottom-left
            normalized.y = -normalized.y;
            gl_Position = vec4(normalized, 0.0, 1.0);
            v_texCoord = a_texCoord;
        }
        '''

        fragment_src = '''
        precision mediump float;
        varying vec2 v_texCoord;
        uniform sampler2D u_texture;
        uniform vec4 u_color;

        void main() {
            vec4 texColor = texture2D(u_texture, v_texCoord);
            gl_FragColor = vec4(u_color.rgb, u_color.a * texColor.a);
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

        # Load texture atlas
        self.texture_id = self._load_texture(self.atlas_path)
        if not self.texture_id:
            print('Failed to load texture atlas')
            return False

        # Get atlas dimensions
        img = Image.open(self.atlas_path)
        self.atlas_width = img.width
        self.atlas_height = img.height

        return True

    def _load_texture(self, image_path):
        img = Image.open(image_path)
        img = np.array(img)

        # Convert BGR to RGB if needed

        # Generate texture
        texture_id = gl.glGenTextures(1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)

        # Set texture parameters
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

        # Upload texture data
        if img.shape[2] == 4:
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, img.shape[1], img.shape[0],
                         0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, img)
        else:
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, img.shape[1], img.shape[0],
                         0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, img)

        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        return texture_id

    def set_viewport(self, width, height):
        self.width = width
        self.height = height

    def get_char_tex_coords(self, char_code):
        """Calculate texture coordinates for a character based on its ASCII code"""
        # Skip characters below our first character
        if char_code < self.FIRST_CHAR:
            return None

        # Calculate index of the character in our atlas
        index = char_code - self.FIRST_CHAR

        # Get row and column in the atlas grid
        row = index // self.CHARS_PER_ROW
        col = index % self.CHARS_PER_ROW

        # Get the texture coordinates (normalized)
        s0 = col * self.CELL_WIDTH / self.atlas_width
        t0 = row * self.CELL_HEIGHT / self.atlas_height
        s1 = (col + 1) * self.CELL_WIDTH / self.atlas_width
        t1 = (row + 1) * self.CELL_HEIGHT / self.atlas_height

        return (s0, t0, s1, t1)

    def render_texts(self, texts):
        """
        Render multiple text strings at once.

        Args:
            texts: List of tuples (text, x, y, scale) where:
                text: String to render
                x, y: Position coordinates
                scale: Optional scale factor (default: 1.0)
        """
        if not self.shader or not self.texture_id or self.width == 0 or self.height == 0:
            return

        if not texts:
            return

        # Enable blending for proper text rendering
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        # Use shader program
        gl.glUseProgram(self.shader)

        # Set color uniform
        color_loc = gl.glGetUniformLocation(self.shader, 'u_color')
        gl.glUniform4f(color_loc, *self.color)

        # Set resolution uniform
        resolution_loc = gl.glGetUniformLocation(self.shader, 'u_resolution')
        gl.glUniform2f(resolution_loc, float(self.width), float(self.height))

        # Set texture uniform
        texture_loc = gl.glGetUniformLocation(self.shader, 'u_texture')
        gl.glUniform1i(texture_loc, 0)

        # Activate texture
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture_id)

        # Get attribute locations
        position_loc = gl.glGetAttribLocation(self.shader, 'a_position')
        texcoord_loc = gl.glGetAttribLocation(self.shader, 'a_texCoord')

        # Set up arrays
        gl.glEnableVertexAttribArray(position_loc)
        gl.glEnableVertexAttribArray(texcoord_loc)

        # Bind VBO
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)

        # Process each text entry
        for text_entry in texts:
            # Unpack the text entry
            if len(text_entry) == 3:
                text, x, y = text_entry
                scale = 1.0
            else:
                text, x, y, scale = text_entry

            # Starting position
            cursor_x, cursor_y = x, y

            for char in text:
                char_code = ord(char)
                tex_coords = self.get_char_tex_coords(char_code)

                if tex_coords is None:
                    # Skip characters not in our atlas
                    cursor_x += int(self.CELL_WIDTH * scale)
                    continue

                s0, t0, s1, t1 = tex_coords

                # Calculate vertex positions
                x0 = cursor_x
                y0 = cursor_y
                x1 = x0 + int(self.CELL_WIDTH * scale)
                y1 = y0 + int(self.CELL_HEIGHT * scale)

                # Create vertex data with interleaved position and texture coordinates
                vertices = np.array([
                    # Position (x,y)   # Texcoord (s,t)
                    x0, y0,            s0, t0,  # bottom-left
                    x1, y0,            s1, t0,  # bottom-right
                    x0, y1,            s0, t1,  # top-left
                    x0, y1,            s0, t1,  # top-left
                    x1, y0,            s1, t0,  # bottom-right
                    x1, y1,            s1, t1,  # top-right
                ], dtype=np.float32)

                # Upload vertex data
                gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STREAM_DRAW)

                # Set up vertex attributes
                stride = 4 * 4  # 4 floats per vertex, 4 bytes per float
                gl.glVertexAttribPointer(position_loc, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, None)
                gl.glVertexAttribPointer(texcoord_loc, 2, gl.GL_FLOAT, gl.GL_FALSE, stride,
                                      gl.ctypes.c_void_p(2 * 4))  # offset of texture coords

                # Draw
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

                # Advance cursor
                cursor_x += int(self.CELL_WIDTH * scale)

        # Clean up
        gl.glDisableVertexAttribArray(position_loc)
        gl.glDisableVertexAttribArray(texcoord_loc)
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glUseProgram(0)
        gl.glDisable(gl.GL_BLEND)

    def render_text(self, text, x, y, scale=1.0):
        """
        Render a single text string (convenience method).

        Args:
            text: String to render
            x, y: Position coordinates
            scale: Optional scale factor (default: 1.0)
        """
        self.render_texts([(text, x, y, scale)])

    def cleanup(self):
        if self.vbo:
            gl.glDeleteBuffers(1, [self.vbo])
            self.vbo = None
        if self.texture_id:
            gl.glDeleteTextures([self.texture_id])
            self.texture_id = None
        if self.shader:
            gl.glDeleteProgram(self.shader)
            self.shader = None
