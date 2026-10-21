"""Build a SCORM 1.2 / 2004 .zip from the course data prepared by lms.scorm.course.

``build_package(data, files)`` returns the zip bytes. ``data`` is the course
JSON the player reads (``static/player/player.js``); ``files`` maps package
paths to bytes (pictures, video, logo). The player, its stylesheet and the
manifest are added here, so a package runs in any SCORM LMS, and outside one
(no LMS found = preview mode).
"""
import html
import io
import json
import os
import zipfile

PLAYER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'player')
PLAYER_FILES = ('player.js', 'player.css')

MANIFEST_12 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="{version}"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 imsmd_rootv1p2p1.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="org_1">
    <organization identifier="org_1">
      <title>{title}</title>
      <item identifier="item_1" identifierref="res_1" isvisible="true">
        <title>{title}</title>{mastery}
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""

MANIFEST_2004 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="{version}"
          xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
          xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
          xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
          xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>
  <organizations default="org_1">
    <organization identifier="org_1">
      <title>{title}</title>
      <item identifier="item_1" identifierref="res_1" isvisible="true">
        <title>{title}</title>{objectives}
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res_1" type="webcontent" adlcp:scormType="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
{font_link}<link rel="stylesheet" href="player.css"/>
<style>
:root {{
  --brand-primary: {primary};
  --brand-secondary: {secondary};
  --brand-bg: {background};
  --brand-slide: {slide};
  --brand-text: {text};
  --brand-button-text: {button_text};
  --brand-font: {font};
}}
</style>
</head>
<body>
<div id="sp-app" class="sp-app"><div class="sp-loading">Loading…</div></div>
<script src="course.js"></script>
<script src="player.js"></script>
</body>
</html>
"""


def _css_value(value, fallback):
    value = (value or '').strip()
    if not value or any(c in value for c in ';{}<>'):
        return fallback
    return value


def render_index(data):
    brand = data.get('branding') or {}
    font_url = brand.get('font_url') or ''
    font_link = ''
    if font_url.startswith('https://fonts.googleapis.com/'):
        font_link = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin=""/>\n'
                     '<link rel="stylesheet" href="%s"/>\n' % html.escape(font_url, quote=True))
    return INDEX_HTML.format(
        title=html.escape(data.get('title') or 'Course'),
        font_link=font_link,
        primary=_css_value(brand.get('primary_color'), '#1f6feb'),
        secondary=_css_value(brand.get('secondary_color'), '#0b3d91'),
        background=_css_value(brand.get('background_color'), '#f4f6f8'),
        slide=_css_value(brand.get('slide_color'), '#ffffff'),
        text=_css_value(brand.get('text_color'), '#1f2933'),
        button_text=_css_value(brand.get('button_text_color'), '#ffffff'),
        font=_css_value(brand.get('font_family'), 'Arial, Helvetica, sans-serif'),
    )


def render_course_js(data):
    # </script> can't appear inside the JSON once escaped like this
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return 'window.SCORM_COURSE = %s;\n' % payload


def render_manifest(data, paths):
    settings = data.get('settings') or {}
    identifier = ''.join(c if c.isalnum() or c in '_-.' else '_' for c in data.get('identifier') or 'course')
    title = html.escape(data.get('title') or 'Course')
    files = '\n'.join('      <file href="%s"/>' % html.escape(p, quote=True) for p in sorted(paths))
    if data.get('scorm_version') == '2004':
        objectives = ''
        if settings.get('require_pass'):
            objectives = (
                '\n        <imsss:sequencing>'
                '\n          <imsss:objectives>'
                '\n            <imsss:primaryObjective objectiveID="primary" satisfiedByMeasure="true">'
                '\n              <imsss:minNormalizedMeasure>%.2f</imsss:minNormalizedMeasure>'
                '\n            </imsss:primaryObjective>'
                '\n          </imsss:objectives>'
                '\n        </imsss:sequencing>' % ((settings.get('passing_score') or 0) / 100.0))
        return MANIFEST_2004.format(identifier=identifier, version=data.get('version') or 1,
                                    title=title, objectives=objectives, files=files)
    mastery = ''
    if settings.get('require_pass'):
        mastery = '\n        <adlcp:masteryscore>%d</adlcp:masteryscore>' % (settings.get('passing_score') or 0)
    return MANIFEST_12.format(identifier=identifier, version=data.get('version') or 1,
                              title=title, mastery=mastery, files=files)


def build_package(data, files=None):
    """Return the SCORM .zip as bytes."""
    files = dict(files or {})
    for name in PLAYER_FILES:
        with open(os.path.join(PLAYER_DIR, name), 'rb') as handle:
            files[name] = handle.read()
    files['index.html'] = render_index(data).encode('utf-8')
    files['course.js'] = render_course_js(data).encode('utf-8')
    paths = list(files)
    files['imsmanifest.xml'] = render_manifest(data, paths).encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        # Manifest first: some LMSs only look at the start of the archive
        archive.writestr('imsmanifest.xml', files.pop('imsmanifest.xml'))
        for path in sorted(files):
            data_bytes = files[path]
            compress = zipfile.ZIP_STORED if path.rsplit('.', 1)[-1].lower() in (
                'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mp3', 'm4a', 'ogg') else zipfile.ZIP_DEFLATED
            archive.writestr(zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0)), data_bytes,
                             compress_type=compress)
    return buffer.getvalue()


def read_package_file(package, path):
    """Return (bytes) of ``path`` inside a built package, or None."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        clean = path.replace('\\', '/').lstrip('/')
        if clean not in archive.namelist():
            return None
        return archive.read(clean)
