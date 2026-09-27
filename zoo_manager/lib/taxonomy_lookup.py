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
import time
from urllib.parse import quote, urlparse

import requests
from lxml import html

_logger = logging.getLogger(__name__)

# Wikimedia throttles clients that don't say who they are and how to reach
# them (https://meta.wikimedia.org/wiki/User-Agent_policy).
USER_AGENT = ('ZooManager/1.1 (https://system.cliffscountrycrafts.com; wildlife park species records) '
              f'python-requests/{requests.__version__}')
TIMEOUT = 20
# Wikimedia serves thumbnails at set widths; other widths are rendered on
# demand and throttled much harder.
IMAGE_WIDTH = 960
# Pause between requests and how long to wait when asked to slow down.
REQUEST_DELAY = 1.0
MAX_RETRY_WAIT = 30
RETRIES = 2
RANKS = ('kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')
MIN_CONFIDENCE = 90
_RANGE_SECTIONS = ('binomial name', 'trinomial name', 'subspecies')
# GBIF's backbone has no class Reptilia: it files reptiles under their orders
# as if those were classes (class Squamata, no order). Put them back under
# Reptilia with the order where it belongs.
REPTILE_ORDERS = ('Squamata', 'Testudines', 'Crocodylia', 'Rhynchocephalia', 'Sphenodontia')


# Wikimedia OAuth 2.0 (https://api.wikimedia.org/wiki/Authentication):
# authenticated requests get 5,000 requests an hour instead of 500.
WIKIMEDIA_TOKEN_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/access_token'
_WIKIMEDIA_HOSTS = ('wikipedia.org', 'wikimedia.org')


class RateLimited(Exception):
    """The server asked us to slow down (HTTP 429) and kept doing so."""


class AuthenticationFailed(Exception):
    """Wikimedia rejected the OAuth credentials."""


def fetch_wikimedia_token(client_id, client_secret):
    """Exchange an OAuth 2.0 client's ID and secret for an access token
    (client credentials grant). Returns (token, seconds until it expires)."""
    response = requests.post(WIKIMEDIA_TOKEN_URL, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, data={
        'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret,
    })
    if response.status_code in (400, 401, 403):
        raise AuthenticationFailed(response.text[:200])
    response.raise_for_status()
    data = response.json()
    return data['access_token'], int(data.get('expires_in') or 3600)


def _is_wikimedia(url):
    host = urlparse(url).hostname or ''
    return any(host == domain or host.endswith('.' + domain) for domain in _WIKIMEDIA_HOSTS)


def _get(url, token=None, **params):
    """GET with retries on HTTP 429. The Wikimedia OAuth token is only ever
    sent to Wikipedia/Wikimedia, never to other sites (e.g. GBIF)."""
    headers = {'User-Agent': USER_AGENT}
    if token and _is_wikimedia(url):
        headers['Authorization'] = f'Bearer {token}'
    for attempt in range(RETRIES + 1):
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, params=params or None, timeout=TIMEOUT, headers=headers)
        if response.status_code == 401 and 'Authorization' in headers:
            raise AuthenticationFailed(url)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        if attempt < RETRIES:
            try:
                wait = int(response.headers.get('Retry-After', 0))
            except ValueError:
                wait = 0
            time.sleep(min(max(wait, 5 * (attempt + 1)), MAX_RETRY_WAIT))
    raise RateLimited(url)


def clean_name(scientific_name):
    """'Calyptorhynchus banksii (except graptogyne)' -> 'Calyptorhynchus banksii'."""
    name = re.sub(r'\(.*?\)', '', scientific_name or '')
    return ' '.join(name.split())


def _gbif_match(scientific_name):
    """GBIF's backbone entry for the name, or None without an exact, confident match."""
    name = clean_name(scientific_name)
    if not name or name.endswith(' spp') or name.endswith(' sp'):
        return None
    data = _get('https://api.gbif.org/v1/species/match', name=name, strict='true').json()
    if data.get('matchType') != 'EXACT' or data.get('confidence', 0) < MIN_CONFIDENCE:
        return None
    return data


def lookup_classification(scientific_name):
    """{rank: name} from GBIF, or {} when GBIF has no exact, confident match."""
    data = _gbif_match(scientific_name)
    if not data:
        return {}
    return fix_reptile_class({rank: data[rank] for rank in RANKS if data.get(rank)})


# IUCN Red List categories as GBIF names them, with their codes.
IUCN_CODES = {
    'EXTINCT': 'EX', 'EXTINCT_IN_THE_WILD': 'EW', 'CRITICALLY_ENDANGERED': 'CR', 'ENDANGERED': 'EN',
    'VULNERABLE': 'VU', 'NEAR_THREATENED': 'NT', 'LEAST_CONCERN': 'LC', 'DATA_DEFICIENT': 'DD',
    'NOT_EVALUATED': 'NE',
}


def lookup_conservation_status(scientific_name):
    """The IUCN Red List category of the species, from GBIF's copy of the Red
    List: {'code': 'VU', 'name': 'Vulnerable', 'url': GBIF page}, or {} when
    it can't be confirmed. A subspecies without its own assessment gets its
    species' category."""
    data = _gbif_match(scientific_name)
    if not data:
        return {}
    for key in dict.fromkeys(filter(None, (data.get('usageKey'), data.get('speciesKey')))):
        try:
            response = _get(f'https://api.gbif.org/v1/species/{key}/iucnRedListCategory')
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                continue
            raise
        if not response.content:
            continue
        category = response.json().get('category')
        if not category:
            continue
        code = response.json().get('code') or IUCN_CODES.get(category) or category
        return {
            'code': code.upper(),
            'name': category.replace('_', ' ').title().replace(' In ', ' in ').replace(' The ', ' the '),
            'url': f'https://www.gbif.org/species/{key}',
        }
    return {}


def fix_reptile_class(taxonomy):
    """{'class': 'Squamata'} -> {'class': 'Reptilia', 'order': 'Squamata'}."""
    if taxonomy.get('class') in REPTILE_ORDERS:
        taxonomy = dict(taxonomy)
        taxonomy.setdefault('order', taxonomy['class'])
        taxonomy['class'] = 'Reptilia'
    return taxonomy


def _wikipedia_title(scientific_name, token=None):
    """The English Wikipedia article for the name (following redirects), or None."""
    data = _get(
        'https://en.wikipedia.org/w/api.php', token=token,
        action='query', titles=clean_name(scientific_name), redirects=1, format='json', formatversion=2,
    ).json()
    pages = data.get('query', {}).get('pages', [])
    if not pages or pages[0].get('missing'):
        return None
    return pages[0]['title']


def _download(url, token=None):
    if url.startswith('//'):
        url = 'https:' + url
    return base64.b64encode(_get(url, token=token).content)


def lookup_images(scientific_name, width=IMAGE_WIDTH, token=None):
    """{'image': b64, 'distribution': b64, 'url': article URL}, with only the
    pictures that were found. `token` is a Wikimedia OAuth access token."""
    title = _wikipedia_title(scientific_name, token)
    if not title:
        return {}
    result = {'url': 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_'))}

    pages = _get(
        'https://en.wikipedia.org/w/api.php', token=token,
        action='query', titles=title, prop='pageimages', piprop='thumbnail', pithumbsize=width,
        format='json', formatversion=2,
    ).json().get('query', {}).get('pages', [])
    thumbnail = pages and pages[0].get('thumbnail', {}).get('source')
    if thumbnail:
        result['image'] = _download(thumbnail, token)

    map_src = _distribution_map_src(title, token)
    if map_src:
        try:
            result['distribution'] = _download(_larger_thumbnail(map_src, width), token)
        except requests.HTTPError:
            # A thumbnail can't be larger than a raster original: use the page's size.
            result['distribution'] = _download(map_src, token)
    return result


def _distribution_map_src(title, token=None):
    parsed = _get(
        'https://en.wikipedia.org/w/api.php', token=token,
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


def wikimedia_username(token):
    """The Wikimedia account the token belongs to (to test the credentials)."""
    data = _get('https://en.wikipedia.org/w/api.php', token=token,
                action='query', meta='userinfo', format='json', formatversion=2).json()
    user = data.get('query', {}).get('userinfo', {})
    if not user or user.get('anon'):
        raise AuthenticationFailed('The token was not accepted.')
    return user.get('name')


def _larger_thumbnail(src, width):
    """Wikimedia thumbnail URLs carry their width ('/250px-'): ask for a bigger one."""
    return re.sub(r'/(\d+)px-', lambda m: f'/{max(int(m.group(1)), width)}px-', src, count=1)
