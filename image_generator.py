import requests
import io
from PIL import Image, ImageDraw, ImageFont
import random

def generate_simple_image(prompt: str) -> io.BytesIO:
    """Generate a simple image based on text prompt"""
    # Create a simple colored image with text
    width, height = 512, 512
    
    # Random background color
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
    bg_color = random.choice(colors)
    
    # Create image
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Add text
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    # Wrap text
    words = prompt.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        test_line = ' '.join(current_line)
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] > width - 40:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    
    if current_line:
        lines.append(' '.join(current_line))
    
    # Draw text lines
    y_offset = (height - len(lines) * 30) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - bbox[2]) // 2
        y = y_offset + i * 30
        draw.text((x, y), line, fill='white', font=font)
    
    # Save to BytesIO
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes

def should_generate_image(text: str) -> bool:
    """Check if the message requests image generation"""
    image_triggers = ['картинка', 'изображение', 'фото', 'рисунок', 'нарисуй', 'покажи']
    return any(trigger in text.lower() for trigger in image_triggers)