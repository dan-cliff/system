"""Look up a species' scientific classification and pictures by scientific name.

Plain Python (only `requests` and `lxml`, both Odoo dependencies) so the same
code runs inside Odoo and in the script that builds the species data file.

- Classification comes from the GBIF Backbone Taxonomy, and is only used when
  GBIF matches the name exactly and confidently.
- The picture is the lead image of the English Wikipedia article.
- The geographic distribution is the first image in the article's taxobox
  after the "Binomial name" / "Trinomial name" / "Subspecies" section, which
  is where Wikipedia puts the range map.
"""
import base64
import logging
import re
from urllib.parse import quote

import requests
from lxml import html

_logger = logging.getLogger(__name__)

USER_AGENT = 'ZooManager/1.0 (Odoo module; wildlife park species records)'
TIMEOUT = 20
RANKS = ('kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')
MIN_CONFIDENCE = 90
_RANGE_SECTIONS = ('binomial name', 'trinomial name', 'subspecies')
# GBIF's backbone has no class Reptilia: it files reptiles under their orders
# as if those were classes (class Squamata, no order). Put them back under
# Reptilia with the order where it belongs.
REPTILE_ORDERS = ('Squamata', 'Testudines', 'Crocodylia', 'Rhynchocephalia', 'Sphenodontia')


def _get(url, **params):
    response = requests.get(url, params=params or None, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT})
    response.raise_for_status()
    return response


def clean_name(scientific_name):
    """'Calyptorhynchus banksii (except graptogyne)' -> 'Calyptorhynchus banksii'."""
    name = re.sub(r'\(.*?\)', '', scientific_name or '')
    return ' '.join(name.split())


def lookup_classification(scientific_name):
    """{rank: name} from GBIF, or {} when GBIF has no exact, confident match."""
    name = clean_name(scientific_name)
    if not name or name.endswith(' spp') or name.endswith(' sp'):
        return {}
    data = _get('https://api.gbif.org/v1/species/match', name=name, strict='true').json()
    if data.get('matchType') != 'EXACT' or data.get('confidence', 0) < MIN_CONFIDENCE:
        return {}
    return fix_reptile_class({rank: data[rank] for rank in RANKS if data.get(rank)})


def fix_reptile_class(taxonomy):
    """{'class': 'Squamata'} -> {'class': 'Reptilia', 'order': 'Squamata'}."""
    if taxonomy.get('class') in REPTILE_ORDERS:
        taxonomy = dict(taxonomy)
        taxonomy.setdefault('order', taxonomy['class'])
        taxonomy['class'] = 'Reptilia'
    return taxonomy


def _wikipedia_title(scientific_name):
    """The English Wikipedia article for the name (following redirects), or None."""
    data = _get(
        'https://en.wikipedia.org/w/api.php',
        action='query', titles=clean_name(scientific_name), redirects=1, format='json', formatversion=2,
    ).json()
    pages = data.get('query', {}).get('pages', [])
    if not pages or pages[0].get('missing'):
        return None
    return pages[0]['title']


def _download(url):
    if url.startswith('//'):
        url = 'https:' + url
    return base64.b64encode(_get(url).content)


def lookup_images(scientific_name, width=800):
    """{'image': b64, 'distribution': b64, 'url': article URL}, with only the
    pictures that were found."""
    title = _wikipedia_title(scientific_name)
    if not title:
        return {}
    result = {'url': 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_'))}

    pages = _get(
        'https://en.wikipedia.org/w/api.php',
        action='query', titles=title, prop='pageimages', piprop='thumbnail', pithumbsize=width,
        format='json', formatversion=2,
    ).json().get('query', {}).get('pages', [])
    thumbnail = pages and pages[0].get('thumbnail', {}).get('source')
    if thumbnail:
        result['image'] = _download(thumbnail)

    map_src = _distribution_map_src(title)
    if map_src:
        try:
            result['distribution'] = _download(_larger_thumbnail(map_src, width))
        except requests.HTTPError:
            # A thumbnail can't be larger than a raster original: use the page's size.
            result['distribution'] = _download(map_src)
    return result


def _distribution_map_src(title):
    parsed = _get(
        'https://en.wikipedia.org/w/api.php',
        action='parse', page=title, prop='text', section=0, redirects=1, format='json', formatversion=2,
    ).json()
    text = parsed.get('parse', {}).get('text')
    if not text:
        return None
    tree = html.fromstring(text)
    infobox = tree.xpath('//table[contains(@class, "infobox") and contains(@class, "biota")]')
    if not infobox:
        return None
    after_name = False
    for row in infobox[0].xpath('.//tr'):
        heading = ' '.join(row.xpath('./th//text()')).strip().lower()
        if any(section in heading for section in _RANGE_SECTIONS):
            after_name = True
            continue
        if after_name:
            images = row.xpath('.//img[@src]')
            if images:
                return images[0].get('src')
    return None


def _larger_thumbnail(src, width):
    """Wikimedia thumbnail URLs carry their width ('/250px-'): ask for a bigger one."""
    return re.sub(r'/(\d+)px-', lambda m: f'/{max(int(m.group(1)), width)}px-', src, count=1)
