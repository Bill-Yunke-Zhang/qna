import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request):
    # Dev: all traffic shares one Docker-internal IP — return a UUID so limits
    # never fire during local development.
    from app.config import settings

    if settings.is_development:
        return str(uuid.uuid4())
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)
