import requests
import io

def generate_simple_image(prompt: str) -> io.BytesIO:
    """Generate AI image using Pollinations API"""
    try:
        # Use Pollinations free API
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        img_bytes = io.BytesIO(response.content)
        img_bytes.seek(0)
        return img_bytes
    except Exception as e:
        print(f"AI image generation failed: {e}")
        # Fallback to simple text image
        from PIL import Image, ImageDraw, ImageFont
        import random
        
        width, height = 512, 512
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        bg_color = random.choice(colors)
        
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.load_default()
        except:
            font = None
        
        text = f"Image: {prompt[:50]}..."
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (width - bbox[2]) // 2
            y = (height - bbox[3]) // 2
            draw.text((x, y), text, fill='white', font=font)
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

def should_generate_image(text: str) -> bool:
    """Check if the message requests image generation"""
    image_triggers = ['картинка', 'изображение', 'фото', 'рисунок', 'нарисуй', 'покажи']
    return any(trigger in text.lower() for trigger in image_triggers)