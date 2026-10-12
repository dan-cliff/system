from .facebook import FacebookProvider
from .instagram import InstagramProvider
from .linkedin import LinkedInProvider
from .tiktok import TikTokProvider
from .twitter import TwitterProvider
from .youtube import YouTubeProvider

PROVIDERS = {
    provider.code: provider
    for provider in (FacebookProvider, TwitterProvider, LinkedInProvider, InstagramProvider,
                     TikTokProvider, YouTubeProvider)
}
PROVIDER_CODES = [(code, provider.label) for code, provider in PROVIDERS.items()]


def get_provider_class(code):
    return PROVIDERS.get(code)
