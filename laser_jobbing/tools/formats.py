# -*- coding: utf-8 -*-
"""File formats used by laser jobs.

Cutting and scoring jobs always produce an .svg file. Engraving jobs produce
a raster image in the format of the picture uploaded by the customer or
employee (or of the template's base picture when nothing was uploaded).
"""
import os

OPERATIONS = [
    ('engrave', 'Engraving'),
    ('cut', 'Cutting'),
    ('score', 'Scoring'),
]
VECTOR_OPERATIONS = ('cut', 'score')

SVG_EXTENSIONS = ('svg',)
RASTER_EXTENSIONS = ('png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff', 'gif', 'heic')

# Pillow format names to save each extension with.
PIL_FORMATS = {
    'png': 'PNG',
    'jpg': 'JPEG',
    'jpeg': 'JPEG',
    'bmp': 'BMP',
    'webp': 'WEBP',
    'tif': 'TIFF',
    'tiff': 'TIFF',
    'gif': 'GIF',
    'heic': 'HEIF',
}
# Formats that can't hold transparency: they get a white background.
OPAQUE_EXTENSIONS = ('jpg', 'jpeg', 'bmp', 'gif')
# Formats every browser shows directly; the others are previewed as PNG.
BROWSER_EXTENSIONS = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg')

MIMETYPES = {
    'svg': 'image/svg+xml',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'bmp': 'image/bmp',
    'webp': 'image/webp',
    'tif': 'image/tiff',
    'tiff': 'image/tiff',
    'gif': 'image/gif',
    'heic': 'image/heic',
}

FONT_EXTENSIONS = ('ttf', 'otf')


def extension(filename):
    """Lower case extension of a file name, without the dot ('' when none)."""
    return os.path.splitext(filename or '')[1].lstrip('.').lower()


def allowed_extensions(operation, element_type='image'):
    """Extensions an uploaded file may have for an operation.

    Cutting and scoring work from vectors, so their artwork is .svg;
    engraving works from pictures.
    """
    if operation in VECTOR_OPERATIONS:
        return SVG_EXTENSIONS
    return RASTER_EXTENSIONS


def accept_attribute(operation):
    """Value for an <input type="file" accept="..."> for the operation."""
    return ','.join('.%s' % ext for ext in allowed_extensions(operation))


def output_extension(operation, source_extension=None):
    """Extension of the file a job produces."""
    if operation in VECTOR_OPERATIONS:
        return 'svg'
    return source_extension if source_extension in RASTER_EXTENSIONS else 'png'
