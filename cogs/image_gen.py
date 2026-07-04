import io
from PIL import Image, ImageDraw

async def generate_progress_bar_image(position_ms, duration_ms):
    # Sleek progress bar image
    width, height = 500, 40
    # Transparent
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Colors (All shades of Pink/White)
    bar_bg = (60, 60, 60, 255)
    pink_bright = (255, 182, 193, 255) # Light Pink
    pink_hot = (255, 105, 180, 255) # Hot Pink
    handle_white = (255, 255, 255, 255)

    bar_x, bar_y = 0, 15
    bar_width = width
    bar_height = 8

    # Background line
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), radius=4, fill=bar_bg)

    # Progress line
    if duration_ms > 0:
        progress = min(position_ms / duration_ms, 1.0)
        curr_w = int(progress * bar_width)
        if curr_w > 0:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + curr_w, bar_y + bar_height), radius=4, fill=pink_hot)

        # Handle
        handle_x = curr_w
        h_rad = 12
        draw.ellipse((handle_x - h_rad, bar_y + 4 - h_rad, handle_x + h_rad, bar_y + 4 + h_rad), fill=handle_white)
        draw.ellipse((handle_x - 5, bar_y + 4 - 5, handle_x + 5, bar_y + 4 + 5), fill=pink_hot)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
