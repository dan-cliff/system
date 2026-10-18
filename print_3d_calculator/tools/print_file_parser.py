"""Read 3D print files and work out filament usage and print time.

Pure Python (no Odoo imports) so it can be unit tested on its own.

Sliced files carry the slicer's own estimates, which are read as-is:

* G-code (``.gcode``, ``.gco``, ``.g``, ``.gx``) from PrusaSlicer, SuperSlicer,
  Slic3r, OrcaSlicer, Bambu Studio, Creality Print, Elegoo/Anycubic slicers,
  Cura, Simplify3D, ideaMaker and KISSlicer. G-code from any other slicer is
  measured by replaying its moves.
* Prusa binary G-code (``.bgcode``).
* Sliced 3MF projects (Bambu Studio / OrcaSlicer ``.gcode.3mf`` or projects
  saved after slicing) and Cura / UltiMaker packages (``.ufp``).

Unsliced models (``.stl``, ``.obj``, ``.amf`` and 3MF projects that were never
sliced) are measured instead: the analysis returns the volume and surface
area of each filament's part of the model so the caller can turn them into an
estimate with its own infill / wall / speed settings.
"""

import io
import json
import math
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from xml.etree import ElementTree

DEFAULT_DIAMETER = 1.75
DEFAULT_DENSITY = 1.24

GCODE_EXTENSIONS = ('.gcode', '.gco', '.g', '.gx')
SUPPORTED_EXTENSIONS = (
    '.gcode.3mf', '.3mf', '.bgcode', '.ufp', '.stl', '.obj', '.amf',
) + GCODE_EXTENSIONS

UNIT_SCALE = {
    'micron': 0.001,
    'millimeter': 1.0,
    'centimeter': 10.0,
    'meter': 1000.0,
    'inch': 25.4,
    'foot': 304.8,
}


class PrintFileError(ValueError):
    """The file can't be read as a 3D print file."""


@dataclass
class FilamentUsage:
    slot: int
    material: str = ''
    colour: str = ''
    name: str = ''
    length_mm: float = 0.0
    weight_g: float = 0.0
    volume_cm3: float = 0.0
    density: float = 0.0
    diameter: float = 0.0
    # Unsliced models only: the share of the model printed in this filament.
    mesh_volume_cm3: float = 0.0
    mesh_area_cm2: float = 0.0
    # True when the slicer reported the weight itself (rather than it being
    # worked out from length with an assumed density).
    weight_reported: bool = False

    def fill_missing(self):
        """Derive weight/length/volume from whichever of them is known."""
        diameter = self.diameter or DEFAULT_DIAMETER
        density = self.density or DEFAULT_DENSITY
        area_mm2 = math.pi * (diameter / 2.0) ** 2
        if not self.volume_cm3:
            if self.length_mm:
                self.volume_cm3 = self.length_mm * area_mm2 / 1000.0
            elif self.weight_g:
                self.volume_cm3 = self.weight_g / density
        if not self.weight_g and self.volume_cm3:
            self.weight_g = self.volume_cm3 * density
        if not self.length_mm and self.volume_cm3:
            self.length_mm = self.volume_cm3 * 1000.0 / area_mm2

    @property
    def used(self):
        return bool(self.weight_g or self.length_mm or self.volume_cm3 or self.mesh_volume_cm3)


@dataclass
class PrintFileAnalysis:
    file_format: str = ''
    slicer: str = ''
    sliced: bool = False
    print_time_s: int = 0
    plate_count: int = 1
    filaments: list = field(default_factory=list)
    # Model geometry (unsliced files, and 3MF projects that carry the mesh).
    volume_cm3: float = 0.0
    surface_area_cm2: float = 0.0
    size_mm: tuple = (0.0, 0.0, 0.0)
    triangle_count: int = 0
    # Slicer settings found in an unsliced project (infill %, wall count, ...).
    settings: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    @property
    def used_filaments(self):
        return [f for f in self.filaments if f.used]

    @property
    def total_weight_g(self):
        return sum(f.weight_g for f in self.filaments)

    @property
    def total_length_mm(self):
        return sum(f.length_mm for f in self.filaments)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def detect_format(data, filename=''):
    name = (filename or '').lower()
    if name.endswith('.gcode.3mf'):
        return '3mf'
    for ext in ('.3mf', '.bgcode', '.ufp', '.stl', '.obj', '.amf'):
        if name.endswith(ext):
            return ext[1:]
    if name.endswith(GCODE_EXTENSIONS):
        return 'gcode'
    # No (or unknown) extension: sniff the content.
    head = data[:512]
    if head.startswith(b'GCDE'):
        return 'bgcode'
    if head.startswith(b'PK'):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            names = []
        if any(n.lower().endswith('.model') for n in names):
            return '3mf'
        if any(n.lower().endswith('.gcode') for n in names):
            return 'ufp'
        if any(n.lower().endswith('.amf') for n in names):
            return 'amf'
    if len(data) >= 84:
        (count,) = struct.unpack_from('<I', data, 80)
        if len(data) == 84 + count * 50:
            return 'stl'
    text = head.decode('latin-1').lstrip().lower()
    if text.startswith('solid') and b'facet' in data[:4096]:
        return 'stl'
    if text.startswith('<?xml') and b'<amf' in data[:2048]:
        return 'amf'
    if re.search(r'^\s*(;|g[0-9]|m[0-9])', text, re.M):
        return 'gcode'
    if re.search(r'^\s*v\s+-?[0-9]', text, re.M):
        return 'obj'
    return ''


def analyse(data, filename=''):
    """Analyse a 3D print file and return a :class:`PrintFileAnalysis`."""
    if not data:
        raise PrintFileError('The file is empty.')
    file_format = detect_format(data, filename)
    parser = {
        'gcode': _analyse_gcode_file,
        'bgcode': _analyse_bgcode,
        '3mf': _analyse_3mf,
        'ufp': _analyse_ufp,
        'stl': _analyse_stl,
        'obj': _analyse_obj,
        'amf': _analyse_amf,
    }.get(file_format)
    if not parser:
        raise PrintFileError(
            'Unsupported file type. Supported types: %s.' % ', '.join(SUPPORTED_EXTENSIONS)
        )
    result = parser(data)
    result.file_format = file_format
    for filament in result.filaments:
        filament.weight_reported = bool(filament.weight_g)
        filament.fill_missing()
    result.filaments = [f for f in result.filaments if f.used] or result.filaments[:1]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_DURATION_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])',
    re.I,
)
_DURATION_UNITS = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}


def parse_duration(text):
    """'1d 2h 3m 4s', '1 hours 2 minutes', '01:02:03' or seconds → seconds."""
    text = (text or '').strip()
    if not text:
        return 0
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        return int(round(float(text)))
    clock = re.fullmatch(r'(?:(\d+):)?(\d{1,2}):(\d{2})', text)
    if clock:
        hours, minutes, seconds = clock.groups()
        return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    total = 0.0
    for value, unit in _DURATION_RE.findall(text):
        total += float(value) * _DURATION_UNITS[unit[0].lower()]
    return int(round(total))


def _numbers(text):
    """All numbers in a comma/semicolon separated list ('1.2, 3;4')."""
    return [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', text or '')]


def _split_list(text):
    """Split a slicer list value ('PLA;PETG', '"A";"B"', 'PLA,PLA')."""
    text = (text or '').strip()
    if not text:
        return []
    sep = ';' if ';' in text else ','
    return [v.strip().strip('"').strip() for v in text.split(sep)]


def _colour(value):
    value = (value or '').strip().strip('"')
    match = re.fullmatch(r'#?([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?', value)
    return '#%s' % match.group(1).upper() if match else ''


def _ensure_slots(filaments, count):
    while len(filaments) < count:
        filaments.append(FilamentUsage(slot=len(filaments) + 1))
    return filaments


def _first(settings, *keys):
    for key in keys:
        value = settings.get(key)
        if value not in (None, ''):
            return value
    return ''


# ─────────────────────────────────────────────────────────────────────────────
# G-code
# ─────────────────────────────────────────────────────────────────────────────

_SLICER_PATTERNS = [
    (re.compile(r'bambu\s*studio', re.I), 'Bambu Studio'),
    (re.compile(r'orca\s*slicer', re.I), 'OrcaSlicer'),
    (re.compile(r'creality\s*print', re.I), 'Creality Print'),
    (re.compile(r'elegoo\s*slicer', re.I), 'ElegooSlicer'),
    (re.compile(r'anycubic\s*slicer', re.I), 'Anycubic Slicer'),
    (re.compile(r'super\s*slicer', re.I), 'SuperSlicer'),
    (re.compile(r'prusa\s*slicer', re.I), 'PrusaSlicer'),
    (re.compile(r'slic3r', re.I), 'Slic3r'),
    (re.compile(r'cura|ultimaker', re.I), 'Cura'),
    (re.compile(r'simplify3d', re.I), 'Simplify3D'),
    (re.compile(r'ideamaker', re.I), 'ideaMaker'),
    (re.compile(r'kisslicer', re.I), 'KISSlicer'),
    (re.compile(r'flashprint', re.I), 'FlashPrint'),
    (re.compile(r'craftware', re.I), 'CraftWare'),
    (re.compile(r'qidi\s*studio', re.I), 'QIDI Studio'),
]


def _detect_slicer(text):
    for pattern, name in _SLICER_PATTERNS:
        match = pattern.search(text)
        if match:
            version = re.search(r'%s[^\d\n]{0,20}v?(\d+(?:\.\d+)+)' % re.escape(match.group(0)), text, re.I)
            return '%s %s' % (name, version.group(1)) if version else name
    return ''


_KV_RE = re.compile(r'^\s*([^=:]+?)\s*[=:]\s*(.*?)\s*$')


def _gcode_comments(text):
    """Collect ``; key = value`` / ``;KEY:value`` comments into a dict.

    Keys are lower-cased. Later values don't overwrite earlier non-empty ones,
    except that the footer stats of PrusaSlicer-style slicers win over header
    placeholders (they're both read and the non-empty one is kept).
    """
    comments = {}
    header_lines = []
    for raw in text.splitlines():
        line = raw.lstrip()
        if not line.startswith(';'):
            continue
        body = line.lstrip(';').strip()
        if len(header_lines) < 60:
            header_lines.append(body)
        # Bambu packs two values on one line:
        # "; model printing time: 10m 27s; total estimated time: 16m 50s"
        for part in body.split('; ') if '; ' in body and ':' in body else [body]:
            match = _KV_RE.match(part)
            if not match:
                continue
            key, value = match.group(1).strip().lower(), match.group(2)
            if len(key) > 80:
                continue
            if value or key not in comments:
                comments[key] = value
    return comments, '\n'.join(header_lines)


def _filaments_from_settings(settings, count=0):
    """Material / colour / density / diameter lists from slicer settings."""
    types = _split_list(_first(settings, 'filament_type', 'filament type'))
    colours = _split_list(_first(settings, 'filament_colour', 'filament_color', 'extruder_colour'))
    densities = _numbers(_first(settings, 'filament_density', 'filament density', 'filamentdensities'))
    diameters = _numbers(_first(settings, 'filament_diameter', 'filament diameter', 'filamentdiameters'))
    names = _split_list(_first(settings, 'filament_settings_id', 'filament_ids'))
    count = max(count, len(types), len(colours) if types else 0)
    filaments = _ensure_slots([], count)
    for i, filament in enumerate(filaments):
        filament.material = types[i] if i < len(types) else (types[0] if len(types) == 1 else '')
        filament.colour = _colour(colours[i]) if i < len(colours) else ''
        filament.name = names[i] if i < len(names) else ''
        if densities:
            filament.density = densities[i] if i < len(densities) else densities[-1]
        if diameters:
            filament.diameter = diameters[i] if i < len(diameters) else diameters[-1]
    return filaments


def _apply_per_slot(filaments, values, attr, scale=1.0):
    if not values:
        return False
    _ensure_slots(filaments, len(values))
    for filament, value in zip(filaments, values):
        setattr(filament, attr, value * scale)
    return True


def _analyse_gcode_text(text, extra_settings=None):
    result = PrintFileAnalysis(sliced=True)
    comments, header = _gcode_comments(text)
    if extra_settings:
        for key, value in extra_settings.items():
            if value or key not in comments:
                comments[key] = value
    result.slicer = _detect_slicer(header) or _detect_slicer(
        ' '.join(comments.get(k, '') for k in ('generated by', 'generated with', 'sliced by', 'flavor'))
    )
    filaments = _filaments_from_settings(comments)
    found_usage = False

    # ── PrusaSlicer / SuperSlicer / OrcaSlicer / Bambu Studio ─────────────
    for key, attr, scale in (
        ('filament used [g]', 'weight_g', 1.0),
        ('total filament weight [g]', 'weight_g', 1.0),
        ('filament used [mm]', 'length_mm', 1.0),
        ('total filament length [mm]', 'length_mm', 1.0),
        ('filament used [cm3]', 'volume_cm3', 1.0),
        # Bambu's "total filament volume [cm^3]" actually holds mm³, and it
        # always reports weight and length too, so it is not read.
    ):
        values = _numbers(comments.get(key))
        if values and any(values):
            found_usage |= _apply_per_slot(filaments, values, attr, scale)
    # Old Slic3r: "filament used = 1234.5mm (2.9cm3)" (one per extruder line)
    if not found_usage and comments.get('filament used'):
        match = re.match(r'([\d.]+)\s*mm', comments['filament used'])
        if match:
            found_usage = _apply_per_slot(filaments, [float(match.group(1))], 'length_mm')
    # ── Cura ──────────────────────────────────────────────────────────────
    if not found_usage and comments.get('filament used'):
        values = re.findall(r'([\d.]+)\s*(mm|m)\b', comments['filament used'])
        if values:
            found_usage = _apply_per_slot(
                filaments, [float(v) * (1.0 if u == 'mm' else 1000.0) for v, u in values], 'length_mm'
            )
    if not found_usage:
        volumes = []
        for i in range(16):
            value = comments.get('extruder_train.%d.material.volume_used' % i)
            if value is None:
                break
            volumes.append(float(_numbers(value)[0]) / 1000.0 if _numbers(value) else 0.0)
        if any(volumes):
            found_usage = _apply_per_slot(filaments, volumes, 'volume_cm3')
    # ── Simplify3D ────────────────────────────────────────────────────────
    if not found_usage and comments.get('plastic weight'):
        found_usage = _apply_per_slot(filaments, _numbers(comments['plastic weight'])[:1], 'weight_g')
    if not found_usage and comments.get('filament length'):
        found_usage = _apply_per_slot(filaments, _numbers(comments['filament length'])[:1], 'length_mm')
    # ── ideaMaker ("Material#1 Used: 1234.5" in mm) ───────────────────────
    if not found_usage:
        lengths = []
        for i in range(1, 17):
            value = comments.get('material#%d used' % i)
            if value is None:
                break
            lengths.append((_numbers(value) or [0.0])[0])
        if any(lengths):
            found_usage = _apply_per_slot(filaments, lengths, 'length_mm')
            for i, filament in enumerate(filaments, start=1):
                diameter = _numbers(comments.get('filament diameter #%d' % i))
                if diameter:
                    filament.diameter = diameter[0]
    # ── KISSlicer ("Ext 1 = 1234.56 mm (2.97 cm^3)") ──────────────────────
    if not found_usage:
        lengths = []
        for i in range(1, 17):
            value = comments.get('ext %d' % i)
            if value is None:
                break
            lengths.append((_numbers(value) or [0.0])[0])
        if any(lengths):
            found_usage = _apply_per_slot(filaments, lengths, 'length_mm')

    # Total weight given but not per filament (e.g. one-extruder footers)
    total_weight = _numbers(_first(comments, 'total filament used [g]', 'total filament weight [g]'))
    if total_weight and not any(f.weight_g for f in filaments) and len(filaments) <= 1:
        _ensure_slots(filaments, 1)[0].weight_g = total_weight[0]
        found_usage = True

    # Cura keeps the filament diameter in its settings block.
    if not any(f.diameter for f in filaments):
        match = re.search(r'material_diameter\s*=\s*([\d.]+)', text[-200000:])
        if match:
            for filament in filaments:
                filament.diameter = float(match.group(1))

    # ── Print time ────────────────────────────────────────────────────────
    for key in (
        'estimated printing time (normal mode)', 'total estimated time', 'estimated printing time',
        'model printing time', 'print.time', 'time', 'build time', 'print time',
        'estimated build time',
    ):
        value = comments.get(key)
        if not value:
            continue
        if key == 'estimated build time' and 'minute' in value.lower():
            seconds = int(round((_numbers(value) or [0])[0] * 60))
        else:
            seconds = parse_duration(value)
        if seconds:
            result.print_time_s = seconds
            break

    if not found_usage or not result.print_time_s:
        measured = _measure_gcode_moves(text)
        if not found_usage and any(measured['extruded']):
            _apply_per_slot(filaments, measured['extruded'], 'length_mm')
            found_usage = True
            result.warnings.append(
                'The slicer did not record filament usage, so it was measured from the G-code moves.'
            )
        if not result.print_time_s and measured['time_s']:
            result.print_time_s = int(round(measured['time_s']))
            result.warnings.append(
                'The slicer did not record a print time, so it was estimated from the G-code moves.'
            )
    result.filaments = filaments
    return result


_WORD_RE = re.compile(r'([A-Z])\s*(-?\d*\.?\d+(?:[eE][-+]?\d+)?)')


def _measure_gcode_moves(text):
    """Replay G-code moves: net extrusion per tool (mm) and a rough time."""
    extruded = [0.0]
    tool = 0
    pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'E': 0.0}
    absolute = True
    absolute_e = True
    feed = 1500.0  # mm/min
    scale = 1.0
    time_s = 0.0
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip().upper()
        if not line:
            continue
        if line[0] == 'T' and line[1:].isdigit():
            tool = int(line[1:])
            _ensure_list(extruded, tool + 1)
            continue
        command = line.split(None, 1)[0]
        if command in ('G0', 'G1', 'G00', 'G01', 'G2', 'G3', 'G02', 'G03'):
            words = dict(_WORD_RE.findall(line[len(command):]))
            if 'F' in words:
                feed = float(words['F']) * scale or feed
            distance_sq = 0.0
            for axis in ('X', 'Y', 'Z'):
                if axis in words:
                    value = float(words[axis]) * scale
                    target = value if absolute else pos[axis] + value
                    distance_sq += (target - pos[axis]) ** 2
                    pos[axis] = target
            if 'E' in words:
                value = float(words['E']) * scale
                delta = value - pos['E'] if absolute_e else value
                pos['E'] = value if absolute_e else pos['E'] + value
                extruded[tool] += delta
                if not distance_sq:
                    distance_sq = delta ** 2
            if distance_sq and feed:
                time_s += math.sqrt(distance_sq) / (feed / 60.0)
        elif command == 'G92':
            words = dict(_WORD_RE.findall(line[3:]))
            for axis, value in words.items():
                if axis in pos:
                    pos[axis] = float(value) * scale
        elif command == 'G90':
            absolute = absolute_e = True
        elif command == 'G91':
            absolute = absolute_e = False
        elif command == 'M82':
            absolute_e = True
        elif command == 'M83':
            absolute_e = False
        elif command == 'G20':
            scale = 25.4
        elif command == 'G21':
            scale = 1.0
        elif command == 'G4':
            words = dict(_WORD_RE.findall(line[2:]))
            if 'S' in words:
                time_s += float(words['S'])
            elif 'P' in words:
                time_s += float(words['P']) / 1000.0
    # Acceleration makes real prints slower than feed-rate maths suggests.
    return {'extruded': [max(e, 0.0) for e in extruded], 'time_s': time_s * 1.15}


def _ensure_list(values, length):
    while len(values) < length:
        values.append(0.0)


def _decode(data):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('latin-1')


def _analyse_gcode_file(data):
    if data.startswith(b'xgcode'):
        # FlashPrint .gx: a binary header (with a preview image) before the G-code.
        (offset,) = struct.unpack_from('<I', data, 20) if len(data) > 24 else (0,)
        if not 0 < offset < len(data):
            offset = data.find(b'\n;') + 1
        data = data[offset:]
    return _analyse_gcode_text(_decode(data))


# ─────────────────────────────────────────────────────────────────────────────
# Prusa binary G-code (.bgcode)
# ─────────────────────────────────────────────────────────────────────────────

_BGCODE_METADATA_BLOCKS = {0, 2, 3, 4}  # file, slicer, printer, print metadata
_BGCODE_THUMBNAIL = 5


def _analyse_bgcode(data):
    if not data.startswith(b'GCDE') or len(data) < 10:
        raise PrintFileError('This is not a valid binary G-code file.')
    (checksum_type,) = struct.unpack_from('<H', data, 8)
    checksum_size = 4 if checksum_type == 1 else 0
    offset = 10
    settings = {}
    while offset + 8 <= len(data):
        block_type, compression, size = struct.unpack_from('<HHI', data, offset)
        offset += 8
        compressed_size = size
        if compression:
            (compressed_size,) = struct.unpack_from('<I', data, offset)
            offset += 4
        params = 6 if block_type == _BGCODE_THUMBNAIL else 2
        payload = data[offset + params: offset + params + compressed_size]
        offset += params + compressed_size + checksum_size
        if block_type not in _BGCODE_METADATA_BLOCKS:
            continue
        if compression == 1:
            try:
                payload = zlib.decompress(payload)
            except zlib.error:
                payload = zlib.decompress(payload, -15)
        elif compression:
            continue  # Heatshrink-compressed metadata isn't used by PrusaSlicer.
        for line in _decode(payload).splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
                if value.strip() or key not in settings:
                    settings[key] = value.strip()
    if not settings:
        raise PrintFileError('No print details were found in this binary G-code file.')
    result = _analyse_gcode_text('', extra_settings=settings)
    result.slicer = result.slicer or _detect_slicer(settings.get('producer', '')) or 'PrusaSlicer'
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Zipped formats: 3MF and UFP
# ─────────────────────────────────────────────────────────────────────────────

def _open_zip(data, what):
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise PrintFileError('This is not a valid %s file.' % what) from e


def _zip_find(archive, *names):
    lookup = {n.lower().lstrip('/'): n for n in archive.namelist()}
    for name in names:
        real = lookup.get(name.lower().lstrip('/'))
        if real:
            return real
    return None


def _analyse_ufp(data):
    archive = _open_zip(data, 'UFP')
    gcode_name = _zip_find(archive, '3D/model.gcode') or next(
        (n for n in archive.namelist() if n.lower().endswith('.gcode')), None
    )
    if not gcode_name:
        raise PrintFileError('This UFP package does not contain any G-code.')
    result = _analyse_gcode_text(_decode(archive.read(gcode_name)))
    result.slicer = result.slicer or 'Cura'
    return result


def _xml_root(payload):
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as e:
        raise PrintFileError('The file contains invalid XML: %s' % e) from e


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _read_project_settings(archive):
    """Slicer settings saved in a 3MF project (Bambu/Orca JSON or Prusa INI)."""
    settings = {}
    name = _zip_find(archive, 'Metadata/project_settings.config')
    if name:
        try:
            raw = json.loads(archive.read(name))
        except ValueError:
            raw = {}
        for key, value in raw.items():
            if isinstance(value, list):
                value = ';'.join(str(v) for v in value)
            settings[key.lower()] = str(value)
    name = _zip_find(archive, 'Metadata/Slic3r_PE.config', 'Metadata/SuperSlicer.config')
    if name:
        for line in _decode(archive.read(name)).splitlines():
            match = _KV_RE.match(line.lstrip(';'))
            if match:
                settings.setdefault(match.group(1).strip().lower(), match.group(2))
    return settings


def _analyse_3mf(data):
    archive = _open_zip(data, '3MF')
    settings = _read_project_settings(archive)
    result = None

    # 1. Bambu Studio / OrcaSlicer slice results.
    slice_info = _zip_find(archive, 'Metadata/slice_info.config')
    if slice_info:
        result = _3mf_slice_info(_xml_root(archive.read(slice_info)), settings)

    # 2. G-code stored inside the project (one file per plate).
    if not result:
        gcode_names = sorted(
            n for n in archive.namelist()
            if n.lower().endswith('.gcode') and not n.lower().endswith('.md5')
        )
        if gcode_names:
            result = _merge_plates([
                _analyse_gcode_text(_decode(archive.read(n)), settings) for n in gcode_names
            ])

    # 3. Not sliced: measure the model.
    if not result:
        return _read_3mf_model(archive, settings)
    try:
        model = _read_3mf_model(archive, settings)
    except PrintFileError:
        return result  # sliced-only export without the mesh
    result.volume_cm3 = model.volume_cm3
    result.surface_area_cm2 = model.surface_area_cm2
    result.size_mm = model.size_mm
    result.triangle_count = model.triangle_count
    result.slicer = model.slicer or result.slicer
    return result


def _merge_plates(plates):
    result = plates[0]
    result.plate_count = len(plates)
    for plate in plates[1:]:
        result.print_time_s += plate.print_time_s
        result.warnings.extend(w for w in plate.warnings if w not in result.warnings)
        _ensure_slots(result.filaments, len(plate.filaments))
        for total, filament in zip(result.filaments, plate.filaments):
            filament.fill_missing()
            total.fill_missing()
            total.length_mm += filament.length_mm
            total.weight_g += filament.weight_g
            total.volume_cm3 += filament.volume_cm3
            total.material = total.material or filament.material
            total.colour = total.colour or filament.colour
    return result


def _3mf_slice_info(root, settings):
    plates = [p for p in root.iter() if _local(p.tag) == 'plate']
    if not plates:
        return None
    result = PrintFileAnalysis(sliced=True)
    version = ''
    for item in root.iter():
        if _local(item.tag) == 'header_item' and item.get('key') == 'X-BBL-Client-Version':
            version = item.get('value', '')
    defaults = _filaments_from_settings(settings)
    slots = {}
    sliced_plates = 0
    for plate in plates:
        meta = {m.get('key'): m.get('value') for m in plate if _local(m.tag) == 'metadata'}
        prediction = parse_duration(meta.get('prediction') or '')
        plate_filaments = [f for f in plate if _local(f.tag) == 'filament']
        if not prediction and not plate_filaments:
            continue
        sliced_plates += 1
        result.print_time_s += prediction
        for element in plate_filaments:
            slot = int(_numbers(element.get('id'))[0]) if _numbers(element.get('id')) else len(slots) + 1
            filament = slots.get(slot)
            if not filament:
                default = defaults[slot - 1] if slot <= len(defaults) else FilamentUsage(slot=slot)
                filament = slots[slot] = FilamentUsage(
                    slot=slot, density=default.density, diameter=default.diameter,
                    name=default.name, material=default.material, colour=default.colour,
                )
            filament.material = element.get('type') or filament.material
            filament.colour = _colour(element.get('color')) or filament.colour
            filament.length_mm += float(element.get('used_m') or 0) * 1000.0
            filament.weight_g += float(element.get('used_g') or 0)
    if not sliced_plates:
        return None
    result.plate_count = sliced_plates
    result.filaments = [slots[k] for k in sorted(slots)]
    result.slicer = 'Bambu Studio %s' % version if version else ''
    return result


class _MeshTotals:
    """Accumulates volume / area / bounds per filament slot."""

    def __init__(self):
        self.volume = {}
        self.area = {}
        self.triangles = 0
        self.lo = [math.inf] * 3
        self.hi = [-math.inf] * 3

    def add_triangle(self, a, b, c, slot):
        self.triangles += 1
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        self.area[slot] = self.area.get(slot, 0.0) + 0.5 * math.sqrt(
            cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2
        )
        # Signed volume of the tetrahedron (origin, a, b, c).
        volume = (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
        self.volume[slot] = self.volume.get(slot, 0.0) + volume
        for point in (a, b, c):
            for i in range(3):
                if point[i] < self.lo[i]:
                    self.lo[i] = point[i]
                if point[i] > self.hi[i]:
                    self.hi[i] = point[i]

    def to_analysis(self, unit_scale=1.0, settings=None):
        result = PrintFileAnalysis(sliced=False, settings=dict(settings or {}))
        if not self.triangles:
            raise PrintFileError('No 3D model was found in this file.')
        volume_scale = unit_scale ** 3 / 1000.0  # → cm³
        area_scale = unit_scale ** 2 / 100.0  # → cm²
        defaults = _filaments_from_settings(settings or {})
        for slot in sorted(self.volume):
            default = defaults[slot - 1] if 0 < slot <= len(defaults) else FilamentUsage(slot=slot)
            result.filaments.append(FilamentUsage(
                slot=slot, material=default.material, colour=default.colour, name=default.name,
                density=default.density, diameter=default.diameter,
                mesh_volume_cm3=abs(self.volume[slot]) * volume_scale,
                mesh_area_cm2=self.area[slot] * area_scale,
            ))
        result.volume_cm3 = sum(f.mesh_volume_cm3 for f in result.filaments)
        result.surface_area_cm2 = sum(f.mesh_area_cm2 for f in result.filaments)
        result.size_mm = tuple(
            round((self.hi[i] - self.lo[i]) * unit_scale, 2) for i in range(3)
        )
        result.triangle_count = self.triangles
        return result


def _transform(matrix_text):
    values = _numbers(matrix_text)
    if len(values) != 12:
        return None
    return values


def _combine(outer, inner):
    """Compose two 3MF transforms (row-vector 3x4): apply inner, then outer."""
    if not inner:
        return outer
    if not outer:
        return inner
    m = [inner[0:3], inner[3:6], inner[6:9], inner[9:12]]
    n = [outer[0:3], outer[3:6], outer[6:9], outer[9:12]]
    out = []
    for row in range(4):
        for col in range(3):
            value = sum(m[row][k] * n[k][col] for k in range(3))
            if row == 3:
                value += n[3][col]
            out.append(value)
    return out


def _apply(matrix, point):
    if not matrix:
        return point
    x, y, z = point
    return (
        x * matrix[0] + y * matrix[3] + z * matrix[6] + matrix[9],
        x * matrix[1] + y * matrix[4] + z * matrix[7] + matrix[10],
        x * matrix[2] + y * matrix[5] + z * matrix[8] + matrix[11],
    )


def _3mf_extruder_map(archive):
    """Which filament each object / part / triangle range prints in."""
    objects, parts, ranges = {}, {}, {}
    name = _zip_find(archive, 'Metadata/model_settings.config')  # Bambu / Orca
    if name:
        for obj in _xml_root(archive.read(name)):
            if _local(obj.tag) != 'object':
                continue
            for child in obj:
                if _local(child.tag) == 'metadata' and child.get('key') == 'extruder':
                    objects[obj.get('id')] = int(_numbers(child.get('value'))[0] or 1)
                elif _local(child.tag) == 'part':
                    for meta in child:
                        if meta.get('key') == 'extruder':
                            parts[(obj.get('id'), child.get('id'))] = int(_numbers(meta.get('value'))[0] or 1)
    name = _zip_find(archive, 'Metadata/Slic3r_PE_model.config')  # PrusaSlicer
    if name:
        for obj in _xml_root(archive.read(name)):
            if _local(obj.tag) != 'object':
                continue
            for child in obj:
                if _local(child.tag) == 'metadata' and child.get('key') == 'extruder':
                    objects[obj.get('id')] = int(_numbers(child.get('value'))[0] or 1)
                elif _local(child.tag) == 'volume':
                    for meta in child:
                        if meta.get('key') == 'extruder' and _numbers(meta.get('value')):
                            ranges.setdefault(obj.get('id'), []).append((
                                int(child.get('firstid', 0)), int(child.get('lastid', 0)),
                                int(_numbers(meta.get('value'))[0]),
                            ))
    return objects, parts, ranges


def _read_3mf_model(archive, settings):
    rels = _zip_find(archive, '_rels/.rels')
    root_name = None
    if rels:
        for rel in _xml_root(archive.read(rels)):
            if rel.get('Type', '').endswith('/3dmodel'):
                root_name = _zip_find(archive, rel.get('Target', ''))
    root_name = root_name or _zip_find(archive, '3D/3dmodel.model') or next(
        (n for n in archive.namelist() if n.lower().endswith('.model')), None
    )
    if not root_name:
        raise PrintFileError('This 3MF file does not contain a 3D model.')

    models = {}

    def load(name):
        key = name.lower().lstrip('/')
        if key not in models:
            real = _zip_find(archive, name)
            if not real:
                models[key] = ({}, [], 1.0, '')
            else:
                root = _xml_root(archive.read(real))
                objects = {}
                for obj in root.iter():
                    if _local(obj.tag) == 'object' and obj.get('id'):
                        objects[obj.get('id')] = obj
                items = [i for i in root.iter() if _local(i.tag) == 'item']
                app = next((
                    (m.text or '') for m in root if _local(m.tag) == 'metadata'
                    and (m.get('name') or '').lower() == 'application'
                ), '')
                models[key] = (objects, items, UNIT_SCALE.get(root.get('unit', 'millimeter'), 1.0), app)
        return models[key]

    objects_by_id, items, unit_scale, application = load(root_name)
    extruder_objects, extruder_parts, extruder_ranges = _3mf_extruder_map(archive)
    totals = _MeshTotals()
    painted = False

    def walk(model_name, object_id, matrix, top_id, part_id, depth=0):
        nonlocal painted
        objects = load(model_name)[0]
        obj = objects.get(object_id)
        if obj is None or depth > 10:
            return
        for child in obj:
            tag = _local(child.tag)
            if tag == 'mesh':
                default_slot = extruder_parts.get((top_id, part_id)) or extruder_objects.get(top_id) or 1
                vertices = []
                triangles = []
                for section in child:
                    if _local(section.tag) == 'vertices':
                        vertices = [
                            _apply(matrix, (float(v.get('x')), float(v.get('y')), float(v.get('z'))))
                            for v in section
                        ]
                    elif _local(section.tag) == 'triangles':
                        triangles = list(section)
                ranges = extruder_ranges.get(object_id, [])
                for index, tri in enumerate(triangles):
                    slot = default_slot
                    for first, last, extruder in ranges:
                        if first <= index <= last:
                            slot = extruder
                            break
                    if not painted and (tri.get('paint_color') or tri.get('slic3rpe:mmu_segmentation')
                                        or any('mmu_segmentation' in k for k in tri.attrib)):
                        painted = True
                    try:
                        totals.add_triangle(
                            vertices[int(tri.get('v1'))], vertices[int(tri.get('v2'))],
                            vertices[int(tri.get('v3'))], slot,
                        )
                    except (IndexError, TypeError, ValueError):
                        continue
            elif tag == 'components':
                for component in child:
                    path = next((v for k, v in component.attrib.items() if _local(k) == 'path'), None)
                    walk(
                        path or model_name, component.get('objectid'),
                        _combine(matrix, _transform(component.get('transform'))),
                        top_id, component.get('objectid') if depth == 0 else part_id, depth + 1,
                    )

    for item in items:
        if item.get('printable', '1') == '0':
            continue
        object_id = item.get('objectid')
        walk(root_name, object_id, _transform(item.get('transform')), object_id, None)

    project = {}
    infill = _first(settings, 'sparse_infill_density', 'fill_density')
    if _numbers(infill):
        project['infill_percent'] = _numbers(infill)[0] * (100.0 if '%' not in infill and _numbers(infill)[0] <= 1 else 1.0)
    walls = _numbers(_first(settings, 'wall_loops', 'perimeters'))
    if walls:
        project['wall_count'] = walls[0]
    result = totals.to_analysis(unit_scale, settings)
    result.settings.update(project)
    result.slicer = _detect_slicer(application) or application
    result.plate_count = 1
    if painted:
        result.warnings.append(
            'The model has painted colours; the filament split between colours is approximate.'
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Mesh files: STL, OBJ, AMF
# ─────────────────────────────────────────────────────────────────────────────

def _analyse_stl(data):
    totals = _MeshTotals()
    is_binary = len(data) >= 84 and len(data) == 84 + struct.unpack_from('<I', data, 80)[0] * 50
    if is_binary:
        (count,) = struct.unpack_from('<I', data, 80)
        unpack = struct.Struct('<12x9f2x').unpack_from
        for i in range(count):
            v = unpack(data, 84 + i * 50)
            totals.add_triangle(v[0:3], v[3:6], v[6:9], 1)
    else:
        coords = re.findall(
            rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', data, re.I
        )
        try:
            points = [(float(x), float(y), float(z)) for x, y, z in coords]
        except ValueError as e:
            raise PrintFileError('The STL file contains invalid coordinates.') from e
        for i in range(0, len(points) - 2, 3):
            totals.add_triangle(points[i], points[i + 1], points[i + 2], 1)
    return totals.to_analysis()


def _analyse_obj(data):
    totals = _MeshTotals()
    vertices = []
    materials = {}
    slot = 1
    for raw in _decode(data).splitlines():
        parts = raw.split()
        if not parts:
            continue
        if parts[0] == 'v' and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == 'usemtl':
            name = ' '.join(parts[1:])
            slot = materials.setdefault(name, len(materials) + 1)
        elif parts[0] == 'f' and len(parts) >= 4:
            indices = []
            for token in parts[1:]:
                index = int(token.split('/')[0])
                indices.append(index - 1 if index > 0 else len(vertices) + index)
            try:
                for i in range(1, len(indices) - 1):
                    totals.add_triangle(
                        vertices[indices[0]], vertices[indices[i]], vertices[indices[i + 1]], slot
                    )
            except IndexError:
                continue
    result = totals.to_analysis()
    names = {v: k for k, v in materials.items()}
    for filament in result.filaments:
        filament.name = names.get(filament.slot, '')
    return result


def _analyse_amf(data):
    if data.startswith(b'PK'):
        archive = _open_zip(data, 'AMF')
        name = next((n for n in archive.namelist() if not n.endswith('/')), None)
        data = archive.read(name) if name else b''
    root = _xml_root(data)
    totals = _MeshTotals()
    materials = {}
    for obj in root.iter():
        if _local(obj.tag) != 'object':
            continue
        for mesh in obj:
            if _local(mesh.tag) != 'mesh':
                continue
            vertices = []
            for vertex in mesh.iter():
                if _local(vertex.tag) == 'coordinates':
                    coords = {_local(c.tag): float(c.text) for c in vertex}
                    vertices.append((coords.get('x', 0.0), coords.get('y', 0.0), coords.get('z', 0.0)))
            for volume in mesh:
                if _local(volume.tag) != 'volume':
                    continue
                material = volume.get('materialid') or '1'
                slot = materials.setdefault(material, len(materials) + 1)
                for tri in volume:
                    if _local(tri.tag) != 'triangle':
                        continue
                    ids = {_local(v.tag): int(v.text) for v in tri}
                    try:
                        totals.add_triangle(vertices[ids['v1']], vertices[ids['v2']], vertices[ids['v3']], slot)
                    except (KeyError, IndexError):
                        continue
    return totals.to_analysis(UNIT_SCALE.get(root.get('unit', 'millimeter'), 1.0))
