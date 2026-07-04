import io
from PIL import Image, ImageDraw, ImageFont

async def generate_progress_bar_image(position_ms, duration_ms):
    width, height = 550, 60
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        stats_font = ImageFont.truetype(font_path, 16)
    except:
        stats_font = ImageFont.load_default()

    bar_bg = (78, 80, 87, 255)
    pink_accent = (255, 105, 180, 255) # Pink
    handle_color = (255, 255, 255, 255)
    text_white = (255, 255, 255, 255)

    bar_x, bar_y = 0, 10
    bar_width = width
    bar_height = 8

    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), radius=4, fill=bar_bg)

    if duration_ms > 0:
        progress = min(position_ms / duration_ms, 1.0)
        current_width = int(progress * bar_width)
        if current_width > 0:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + current_width, bar_y + bar_height), radius=4, fill=pink_accent)

        handle_x = current_width
        handle_radius = 12
        draw.ellipse((handle_x - handle_radius, bar_y + 4 - handle_radius, handle_x + handle_radius, bar_y + 4 + handle_radius), fill=handle_color)
        draw.ellipse((handle_x - 5, bar_y + 4 - 5, handle_x + 5, bar_y + 4 + 5), fill=pink_accent)

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
