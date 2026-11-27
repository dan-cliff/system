# -*- coding: utf-8 -*-
"""Build the picture of engraving jobs.

The picture is drawn at the template's resolution (dots per inch) and saved
in the format of the picture the customer or employee uploaded: png, jpg,
jpeg, bmp, webp, tif, tiff, gif or heic. HEIC needs the pillow-heif library
on the server; without it a single uploaded HEIC picture is passed through
unchanged, and anything that needs drawing on it asks for another format.
"""
import io

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .formats import OPAQUE_EXTENSIONS, PIL_FORMATS

# Odoo preloads only Pillow's most common formats (odoo/tools/image.py); engraving
# also takes WebP and TIFF pictures, so register those two plugins.
from PIL import TiffImagePlugin, WebPImagePlugin  # noqa: E402,F401 isort:skip

try:  # Optional: lets Pillow read and write HEIC pictures.
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - depends on the server
    HEIF_SUPPORTED = False

# Largest picture a job may produce (about 1 m x 1 m at 254 dpi).
MAX_PIXELS = 100_000_000
DPI_EXTENSIONS = ('png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp')
LINE_SPACING = 0.2


class RasterError(ValueError):
    """The picture can't be read or made."""


def mm_to_px(mm, dpi):
    return max(1, int(round(mm * dpi / 25.4)))


def open_image(data):
    """Open picture data, turned upright from its EXIF orientation."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Image.DecompressionBombError as error:
        raise RasterError('The picture is too large.') from error
    except Exception as error:  # noqa: BLE001 - Pillow raises many kinds
        raise RasterError('The picture could not be read. Please upload a png, jpg, jpeg, bmp, '
                          'webp, tif, tiff, gif or heic file.') from error
    try:
        image = ImageOps.exif_transpose(image)
    except Exception:  # noqa: BLE001 - broken EXIF data: keep it as it is
        pass
    return image


def image_size(data):
    """(width, height) in pixels and the dpi of picture data (dpi may be None)."""
    image = open_image(data)
    dpi = image.info.get('dpi')
    return image.size, (float(dpi[0]) if dpi and dpi[0] else None)


def to_png(data, max_size=1600):
    """A PNG preview of any picture this module reads."""
    image = open_image(data)
    image.thumbnail((max_size, max_size))
    if image.mode not in ('RGB', 'RGBA', 'L', 'LA'):
        image = image.convert('RGBA')
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def _fitted(image, box_size, mode):
    """The picture scaled into a box (contain: whole picture; cover: fills, cropped)."""
    box_w, box_h = box_size
    width, height = image.size
    scale = (max if mode == 'cover' else min)(box_w / width, box_h / height)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    image = image.resize(size, Image.Resampling.LANCZOS)
    if mode == 'cover':
        left, top = (size[0] - box_w) // 2, (size[1] - box_h) // 2
        image = image.crop((left, top, left + box_w, top + box_h))
    return image


def _paste(canvas, image, box, mode):
    """Paste a picture into box (x, y, w, h in px), centred."""
    x, y, w, h = box
    image = _fitted(image.convert('RGBA'), (w, h), mode)
    offset = (x + (w - image.size[0]) // 2, y + (h - image.size[1]) // 2)
    canvas.alpha_composite(image, dest=(max(offset[0], 0), max(offset[1], 0)),
                           source=(max(-offset[0], 0), max(-offset[1], 0)))


def load_font(font_data, size_px):
    if font_data:
        try:
            return ImageFont.truetype(io.BytesIO(font_data), size_px)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size_px)
    except TypeError:  # pragma: no cover - Pillow < 10.1
        return ImageFont.load_default()


def _draw_text(canvas, element, box, dpi):
    text = element.get('text') or ''
    if not element.get('multiline'):
        text = ' '.join(text.splitlines())
    if not text.strip():
        return
    x, y, w, h = box
    align = element.get('align') or 'center'
    draw = ImageDraw.Draw(canvas)
    size = mm_to_px(max(element.get('font_size') or 5.0, 0.1), dpi)

    def measure(size_px):
        font = load_font(element.get('font_data'), size_px)
        spacing = int(size_px * LINE_SPACING)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
        return font, spacing, bbox

    font, spacing, bbox = measure(size)
    if element.get('auto_fit', True):
        for _attempt in range(4):
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if text_w <= w and text_h <= h:
                break
            size = max(1, int(size * min(w / max(text_w, 1), h / max(text_h, 1))))
            font, spacing, bbox = measure(size)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if align == 'left':
        left = x
    elif align == 'right':
        left = x + w - text_w
    else:
        left = x + (w - text_w) / 2
    top = y + (h - text_h) / 2
    try:
        color = ImageColor.getrgb(element.get('color') or '#000000')
    except ValueError:
        color = (0, 0, 0)
    if len(color) == 3:
        color = color + (255,)
    draw.multiline_text((left - bbox[0], top - bbox[1]), text, font=font, fill=color,
                        spacing=spacing, align=align)


def build_raster(spec, extension):
    """The engraving picture of a job, as bytes in the given file extension.

    spec: as for svg_tools.build_svg, plus 'dpi' and 'grayscale'; image
    elements hold picture data.
    """
    pil_format = PIL_FORMATS.get(extension)
    if not pil_format:
        raise RasterError('Engraving files can be png, jpg, jpeg, bmp, webp, tif, tiff, gif or heic.')
    if pil_format == 'HEIF' and not HEIF_SUPPORTED:
        raise RasterError('HEIC pictures need the pillow-heif library on the server. '
                          'Please upload a jpg or png picture instead.')
    dpi = max(int(spec.get('dpi') or 300), 25)
    width, height = mm_to_px(spec['width'], dpi), mm_to_px(spec['height'], dpi)
    if width * height > MAX_PIXELS:
        raise RasterError('The engraving is too large at %s dpi: lower the template\'s resolution.' % dpi)
    opaque = extension in OPAQUE_EXTENSIONS
    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255 if opaque else 0))

    base = spec.get('base')
    if base and base.get('data'):
        _paste(canvas, open_image(base['data']), (0, 0, width, height), 'contain')

    for element in spec.get('elements') or []:
        box = (
            int(round(element['x'] * dpi / 25.4)), int(round(element['y'] * dpi / 25.4)),
            mm_to_px(element['w'], dpi), mm_to_px(element['h'], dpi),
        )
        if element['type'] == 'text':
            _draw_text(canvas, element, box, dpi)
        elif element.get('image'):
            _paste(canvas, open_image(element['image']), box, element.get('fit') or 'contain')

    if opaque:
        flat = Image.new('RGBA', canvas.size, (255, 255, 255, 255))
        flat.alpha_composite(canvas)
        canvas = flat.convert('L' if spec.get('grayscale') else 'RGB')
    elif spec.get('grayscale'):
        canvas = canvas.convert('LA')
        if pil_format in ('WEBP', 'HEIF'):  # no grey + alpha mode: back to RGBA, still grey
            canvas = canvas.convert('RGBA')
    if pil_format == 'GIF':
        canvas = canvas.convert('P', palette=Image.Palette.ADAPTIVE) if canvas.mode != 'L' else canvas
    options = {'dpi': (dpi, dpi)} if extension in DPI_EXTENSIONS else {}
    if pil_format == 'JPEG':
        options['quality'] = 95
    if pil_format == 'WEBP':
        options['lossless'] = True
    out = io.BytesIO()
    canvas.save(out, pil_format, **options)
    return out.getvalue()
