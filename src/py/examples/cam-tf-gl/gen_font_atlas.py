#!/usr/bin/env python3

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import os

def generate_monospace_font_atlas(font_path, font_size, output_path, first_char=32, num_chars=95):
    try:
        # Try to load a monospace font
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f'Font {font_path} not found. Using default font.')
        font = ImageFont.load_default()

    # Fixed cell size (make it a bit larger than font_size to ensure all glyphs fit)
    cell_width = font_size
    cell_height = font_size + 4

    # Calculate grid dimensions
    chars_per_row = 16  # 16 columns makes it easy to find characters (hex-like layout)
    rows_needed = (num_chars + chars_per_row - 1) // chars_per_row  # Ceiling division

    # Create atlas dimensions
    atlas_width = chars_per_row * cell_width
    atlas_height = rows_needed * cell_height

    # Create a blank atlas image with transparency
    atlas = np.zeros((atlas_height, atlas_width, 4), dtype=np.uint8)

    # Draw each character in the grid
    for i in range(num_chars):
        char_code = first_char + i
        char = chr(char_code)

        # Calculate position in the grid
        row = i // chars_per_row
        col = i % chars_per_row

        # Calculate pixel coordinates
        x = col * cell_width
        y = row * cell_height

        # Create a temporary image for this character
        char_img = Image.new('RGBA', (cell_width, cell_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(char_img)

        # Draw the character centered in the cell
        # Get character dimensions to center it
        text_bbox = font.getbbox(char)
        if text_bbox:
            char_width = text_bbox[2] - text_bbox[0]
            char_height = text_bbox[3] - text_bbox[1]
            x_offset = (cell_width - char_width) // 2
            y_offset = (cell_height - char_height) // 2
        else:
            # For space or empty characters
            x_offset = 0
            y_offset = 0

        draw.text((x_offset, y_offset), char, font=font, fill=(255, 255, 255, 255))

        # Convert to numpy array and place in atlas
        char_array = np.array(char_img)
        atlas[y:y+cell_height, x:x+cell_width] = char_array

    # Save the atlas
    cv2.imwrite(output_path, atlas)

    print(f'Monospace font atlas generated: {output_path}')
    print(f'Atlas dimensions: {atlas_width}x{atlas_height}, Cell size: {cell_width}x{cell_height}')
    print(f'Characters per row: {chars_per_row}, Total characters: {num_chars}')
    print(f'First character: ASCII {first_char} ({chr(first_char)})')

    # Return the parameters needed for rendering text
    return {
        'atlas_width': atlas_width,
        'atlas_height': atlas_height,
        'cell_width': cell_width,
        'cell_height': cell_height,
        'chars_per_row': chars_per_row,
        'first_char': first_char,
        'num_chars': num_chars
    }

if __name__ == '__main__':
    # Default monospace system fonts on different operating systems
    possible_mono_fonts = [
        # Linux
        '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        # macOS
        '/Library/Fonts/Courier New.ttf',
        '/Library/Fonts/Monaco.ttf',
        # Windows
        'C:\\Windows\\Fonts\\consola.ttf',  # Consolas
        'C:\\Windows\\Fonts\\cour.ttf',     # Courier New
        # Fallbacks
        'LiberationMono-Regular.ttf',
        'DejaVuSansMono.ttf',
        'consola.ttf',
        'cour.ttf'
    ]

    # Find the first available monospace font
    font_path = None
    for path in possible_mono_fonts:
        if os.path.exists(path):
            font_path = path
            break

    if font_path is None:
        print('Warning: No monospace font found. Using PIL default font.')
        font_path = ''
    else:
        print(f'Using font: {font_path}')

    # Generate the atlas with a font size of 16 pixels
    params = generate_monospace_font_atlas(
        font_path=font_path,
        font_size=16,
        output_path='font_atlas.png',
        first_char=32,   # Start with space character
        num_chars=95     # Cover ASCII 32-126
    )

    # Print the values to be used in text_renderer.py
    print("\nUse these values in your text renderer:")
    print(f"FIRST_CHAR = {params['first_char']}  # ASCII code of first character")
    print(f"CELL_WIDTH = {params['cell_width']}  # Width of each character cell")
    print(f"CELL_HEIGHT = {params['cell_height']}  # Height of each character cell")
    print(f"CHARS_PER_ROW = {params['chars_per_row']}  # Number of characters per row in atlas")
