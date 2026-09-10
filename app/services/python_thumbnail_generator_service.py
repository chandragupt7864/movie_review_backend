import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from app.config import PROJECT_ROOT, settings

class PythonThumbnailGeneratorService:
    def enhance_image(self, image: Image.Image) -> Image.Image:
        # Increase contrast
        contrast = ImageEnhance.Contrast(image)
        image = contrast.enhance(1.25)
        # Increase saturation (color)
        color = ImageEnhance.Color(image)
        image = color.enhance(1.3)
        # Sharpen slightly
        sharpness = ImageEnhance.Sharpness(image)
        image = sharpness.enhance(1.2)
        return image

    def create_blurred_background(self, image_path: str, size: tuple[int, int]) -> Image.Image:
        bg_w, bg_h = size
        try:
            bg_img = Image.open(image_path).convert("RGBA")
        except Exception:
            # Fallback to dark grey canvas if file cannot be loaded
            bg_img = Image.new("RGBA", size, (30, 30, 30, 255))
            return bg_img

        # Resize and crop to fill
        img_w, img_h = bg_img.size
        aspect_canvas = bg_w / bg_h
        aspect_img = img_w / img_h

        if aspect_img > aspect_canvas:
            # Image is wider than canvas: fit height, crop width
            new_h = bg_h
            new_w = int(img_w * (bg_h / img_h))
            bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            x_offset = (new_w - bg_w) // 2
            bg_img = bg_img.crop((x_offset, 0, x_offset + bg_w, bg_h))
        else:
            # Image is taller than canvas: fit width, crop height
            new_w = bg_w
            new_h = int(img_h * (bg_w / img_w))
            bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            y_offset = (new_h - bg_h) // 2
            bg_img = bg_img.crop((0, y_offset, bg_w, y_offset + bg_h))

        # Apply Gaussian Blur
        blur_radius = settings.shorts_background_blur
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Add dark overlay
        overlay = Image.new("RGBA", bg_img.size, (0, 0, 0, int(abs(settings.shorts_background_darkness) * 255)))
        return Image.alpha_composite(bg_img, overlay)

    def paste_image_with_shadow(self, canvas: Image.Image, foreground_image: Image.Image, position: tuple[int, int]) -> Image.Image:
        x, y = position
        fg_w, fg_h = foreground_image.size

        # Create shadow layer
        shadow_offset = 15
        shadow_blur = 20
        shadow_mask = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_mask)
        
        # Draw dark rectangle where foreground image will be, offset slightly
        shadow_draw.rectangle(
            [x + shadow_offset, y + shadow_offset, x + fg_w + shadow_offset, y + fg_h + shadow_offset],
            fill=(0, 0, 0, 160)
        )
        
        # Blur the shadow
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
        
        # Merge shadow onto canvas
        canvas = Image.alpha_composite(canvas, shadow_mask)

        # Draw a subtle border on the foreground image to pop it out
        border_width = 8
        bordered_fg = Image.new("RGBA", (fg_w + border_width * 2, fg_h + border_width * 2), (255, 255, 255, 255))
        bordered_fg.paste(foreground_image, (border_width, border_width))

        # Paste the bordered foreground onto the canvas
        canvas.paste(bordered_fg, (x - border_width, y - border_width), bordered_fg)
        return canvas

    def draw_bold_text(
        self,
        canvas: Image.Image,
        text: str,
        position_y: int,
        max_width: int,
        font_size: int,
        fill: tuple[int, int, int, int] = (255, 255, 255, 255),
        stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255),
        stroke_width: int = 6
    ) -> int:
        draw = ImageDraw.Draw(canvas)
        font = self._load_bold_font(font_size)

        # Wrap text
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            # get width
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))

        # Draw lines
        canvas_w, canvas_h = canvas.size
        curr_y = position_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            
            # Center horizontally
            line_x = (canvas_w - line_w) // 2

            # Draw outline/stroke using classic fallback offset drawing or Pillow native stroke
            try:
                draw.text(
                    (line_x, curr_y),
                    line,
                    font=font,
                    fill=fill,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill
                )
            except TypeError:
                # Fallback outline drawing method
                for ox in range(-stroke_width, stroke_width + 1):
                    for oy in range(-stroke_width, stroke_width + 1):
                        if ox * ox + oy * oy <= stroke_width * stroke_width:
                            draw.text((line_x + ox, curr_y + oy), line, font=font, fill=stroke_fill)
                draw.text((line_x, curr_y), line, font=font, fill=fill)

            curr_y += line_h + 20 # Line spacing

        return curr_y

    def generate_thumbnail(self, movie_row: dict, references: list, output_path: str) -> dict:
        movie_id = movie_row["id"]
        title = movie_row.get("movie_title") or "Movie"
        
        canvas_w = settings.thumbnail_width
        canvas_h = settings.thumbnail_height
        canvas_size = (canvas_w, canvas_h)

        # 1. Select background reference
        bg_ref = None
        for ref in references:
            if ref["type"] in ["backdrop", "video_frame"]:
                bg_ref = ref
                break
        if not bg_ref and references:
            bg_ref = references[0]

        # Resolve paths
        bg_local_path = None
        if bg_ref:
            bg_local_path = str(PROJECT_ROOT / bg_ref["local_path"])

        # 2. Create Background (blurred and darkened)
        canvas = self.create_blurred_background(bg_local_path, canvas_size)
        draw = ImageDraw.Draw(canvas)

        # 3. Select center/foreground reference
        fg_ref = None
        for ref in references:
            if ref["type"] == "poster":
                fg_ref = ref
                break
        if not fg_ref:
            for ref in references:
                if ref["type"] in ["video_frame", "trailer_thumbnail"]:
                    fg_ref = ref
                    break
        if not fg_ref and references:
            fg_ref = references[0]

        # Paste foreground image at center
        fg_used_local = None
        if fg_ref:
            try:
                fg_local_path = str(PROJECT_ROOT / fg_ref["local_path"])
                fg_img = Image.open(fg_local_path).convert("RGBA")
                fg_img = self.enhance_image(fg_img)

                # Scale foreground image to fit nicely in center
                # E.g. width = 75% of canvas width
                target_w = int(canvas_w * 0.72)
                orig_w, orig_h = fg_img.size
                target_h = int(orig_h * (target_w / orig_w))
                
                # If target height exceeds 55% of canvas height, downscale
                if target_h > int(canvas_h * 0.55):
                    target_h = int(canvas_h * 0.50)
                    target_w = int(orig_w * (target_h / orig_h))

                fg_img = fg_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                fg_x = (canvas_w - target_w) // 2
                fg_y = int(canvas_h * 0.22) # Start slightly down

                canvas = self.paste_image_with_shadow(canvas, fg_img, (fg_x, fg_y))
                fg_used_local = fg_ref["local_path"]
            except Exception as e:
                # If foreground paste fails, log it and proceed
                fg_used_local = None

        # 4. Add particle/accent overlay
        # Bottom gradient overlay (draw a black-red fade at bottom)
        gradient = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(gradient)
        for y_coord in range(int(canvas_h * 0.7), canvas_h):
            alpha = int((y_coord - int(canvas_h * 0.7)) / (canvas_h * 0.3) * 190)
            g_draw.line([(0, y_coord), (canvas_w, y_coord)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, gradient)

        # 5. Add text banner
        # Text hook
        thumbnail_text = None
        sd = movie_row.get("script_data_json") or {}
        if isinstance(sd, dict):
            thumbnail_text = sd.get("thumbnail_text")

        if not thumbnail_text:
            # Fallbacks
            thumbnail_text = f"MUST WATCH {title.upper()}!"

        # Draw main hook text at bottom area
        text_y = int(canvas_h * 0.72)
        end_y = self.draw_bold_text(
            canvas=canvas,
            text=thumbnail_text.upper(),
            position_y=text_y,
            max_width=canvas_w - 100,
            font_size=82,
            fill=(255, 235, 59, 255), # Yellow
            stroke_fill=(0, 0, 0, 255),
            stroke_width=8
        )

        # 6. Add Small Badges
        # Add badge like "HINDI REVIEW" or "WATCH NOW"
        badge_y = end_y + 15
        if badge_y < canvas_h - 100:
            badge_text = "WATCH NOW"
            self.draw_bold_text(
                canvas=canvas,
                text=badge_text,
                position_y=badge_y,
                max_width=canvas_w - 200,
                font_size=42,
                fill=(255, 255, 255, 255), # White
                stroke_fill=(229, 57, 53, 255), # Red border
                stroke_width=4
            )

        # 7. Add YouTube Shorts Badge at Top Left
        # Draw a red rounded rect with "SHORTS" inside
        shorts_badge = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        sb_draw = ImageDraw.Draw(shorts_badge)
        sb_draw.rounded_rectangle(
            [40, 40, 260, 100],
            radius=15,
            fill=(229, 57, 53, 255), # Red
            outline=(255, 255, 255, 255),
            width=3
        )
        canvas = Image.alpha_composite(canvas, shorts_badge)

        # Draw "SHORTS" text in the badge
        font_shorts = self._load_bold_font(34)
        draw = ImageDraw.Draw(canvas)
        draw.text((80, 50), "SHORTS", font=font_shorts, fill=(255, 255, 255, 255))

        # Save final image as PNG
        resolved_out = Path(output_path)
        if not resolved_out.is_absolute():
            resolved_out = PROJECT_ROOT / resolved_out
        resolved_out.parent.mkdir(parents=True, exist_ok=True)
        
        # Save as RGB to save file space and ensure compatibility
        canvas.convert("RGB").save(resolved_out, "JPEG", quality=90)

        return {
            "output_path": self._to_relative_path(resolved_out),
            "width": canvas_w,
            "height": canvas_h,
            "style": "viral_shorts_movie_thumbnail",
            "text_used": thumbnail_text,
            "references_used": [ref["local_path"] for ref in references],
            "foreground_used": fg_used_local,
            "generated_by": "python_pillow_opencv"
        }

    def _load_bold_font(self, size: int) -> ImageFont.ImageFont:
        font_paths = [
            r"C:\Windows\Fonts\impact.ttf",        # Windows
            r"C:\Windows\Fonts\arialbd.ttf",       # Windows Bold Arial
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", # Linux
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        
        # Fallback to default
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    @staticmethod
    def _to_relative_path(path: Path) -> str:
        try:
            return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")
