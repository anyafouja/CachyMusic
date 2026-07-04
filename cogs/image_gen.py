import asyncio
import io
from PIL import Image, ImageDraw, ImageFont

async def generate_now_playing_image(track_title, author, requester_name, vc_name, queue_size, volume, loop_status, position_ms, duration_ms):
    # Discord dark theme background color
    bg_color = (49, 51, 56, 255)
    width, height = 600, 320
    image = Image.new('RGBA', (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # Try to load fonts
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        font_bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        header_font = ImageFont.truetype(font_bold_path, 22)
        title_font = ImageFont.truetype(font_bold_path, 20)
        text_font = ImageFont.truetype(font_path, 16)
        stats_font = ImageFont.truetype(font_path, 14)
    except:
        header_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        stats_font = ImageFont.load_default()

    # Pink Theme Colors
    pink_accent = (255, 105, 180, 255) # Hot Pink
    text_white = (255, 255, 255, 255)
    text_gray = (181, 186, 189, 255)
    bar_bg = (78, 80, 87, 255)
    pink_line = (255, 182, 193, 255) # Light Pink

    # Draw "Now playing"
    draw.text((25, 20), "Now playing", font=header_font, fill=pink_accent)

    # Draw separator line
    draw.line((25, 55, width - 25, 55), fill=(60, 62, 66, 255), width=1)

    # Draw Title
    draw.text((25, 75), track_title[:45], font=title_font, fill=pink_accent)

    # Draw "Added by" with pill
    draw.ellipse((25, 115, 30, 120), fill=text_gray) # bullet
    req_label = f"Added by @{requester_name}"
    # Simple pill background for requester
    try:
        text_bbox = draw.textbbox((45, 110), req_label, font=text_font)
        draw.rounded_rectangle((text_bbox[0]-5, text_bbox[1]-2, text_bbox[2]+5, text_bbox[3]+2), radius=5, fill=(60, 64, 100, 255))
    except: pass
    draw.text((45, 110), req_label, font=text_font, fill=text_white)

    # Draw "Channel" with pill
    draw.ellipse((25, 145, 30, 150), fill=text_gray) # bullet
    vc_label = f"Channel: {vc_name}"
    try:
        text_bbox = draw.textbbox((45, 140), vc_label, font=text_font)
        draw.rounded_rectangle((text_bbox[0]-5, text_bbox[1]-2, text_bbox[2]+5, text_bbox[3]+2), radius=5, fill=(60, 64, 100, 255))
    except: pass
    draw.text((45, 140), vc_label, font=text_font, fill=text_white)

    # Stats line
    stats_text = f"Queue Size: {queue_size}  ·  Volume: {volume}%  ·  Loop: {loop_status}"
    draw.text((25, 185), stats_text, font=stats_font, fill=text_gray)

    # Progress Bar (Graphical)
    bar_x, bar_y = 25, 240
    bar_width = width - 50
    bar_height = 6

    # Background line
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), radius=3, fill=bar_bg)

    # Progress line
    if duration_ms > 0:
        progress = min(position_ms / duration_ms, 1.0)
        current_width = int(progress * bar_width)
        if current_width > 0:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + current_width, bar_y + bar_height), radius=3, fill=pink_accent)

        # Handle (The circle)
        handle_x = bar_x + current_width
        handle_radius = 8
        draw.ellipse((handle_x - handle_radius, bar_y + 3 - handle_radius, handle_x + handle_radius, bar_y + 3 + handle_radius), fill=(255, 255, 255, 255))
        # Inner part of handle
        draw.ellipse((handle_x - 3, bar_y + 3 - 3, handle_x + 3, bar_y + 3 + 3), fill=pink_accent)

    # Timestamps
    def format_ms(ms):
        seconds = ms // 1000
        minutes, sec = divmod(seconds, 60)
        return f"{minutes}:{sec:02}"

    draw.text((bar_x, bar_y + 15), format_ms(position_ms), font=stats_font, fill=text_gray)
    draw.text((bar_x + bar_width - 35, bar_y + 15), format_ms(duration_ms), font=stats_font, fill=text_gray)

    # Save to buffer
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
