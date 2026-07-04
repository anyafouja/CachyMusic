import io
from PIL import Image, ImageDraw, ImageFont

async def generate_progress_bar_image(position_ms, duration_ms):
    # Precise graphical progress bar matching the reference image style
    width, height = 550, 60
    # Transparent background for seamless embedding
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Try to load font for timestamps
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        stats_font = ImageFont.truetype(font_path, 16)
    except:
        stats_font = ImageFont.load_default()

    # Colors (Pink Theme as requested)
    bar_bg = (78, 80, 87, 255)
    pink_accent = (255, 105, 180, 255) # Pink
    handle_color = (255, 255, 255, 255)
    text_white = (255, 255, 255, 255)

    bar_y = 10
    bar_height = 8

    # Background line
    draw.rounded_rectangle((0, bar_y, width, bar_y + bar_height), radius=4, fill=bar_bg)

    # Progress line
    if duration_ms > 0:
        progress = min(position_ms / duration_ms, 1.0)
        curr_w = int(progress * width)
        if curr_w > 0:
            draw.rounded_rectangle((0, bar_y, curr_w, bar_y + bar_height), radius=4, fill=pink_accent)

        # Handle (The circle)
        handle_x = curr_w
        draw.ellipse((handle_x - 12, bar_y + 4 - 12, handle_x + 12, bar_y + 4 + 12), fill=handle_color)
        draw.ellipse((handle_x - 6, bar_y + 4 - 6, handle_x + 6, bar_y + 4 + 6), fill=pink_accent)

    # Timestamps at the ends
    def format_ms(ms):
        seconds = ms // 1000
        minutes, sec = divmod(seconds, 60)
        return f"{minutes}:{sec:02}"

    draw.text((0, bar_y + 25), format_ms(position_ms), font=stats_font, fill=text_white)
    draw.text((width - 45, bar_y + 25), format_ms(duration_ms), font=stats_font, fill=text_white)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
