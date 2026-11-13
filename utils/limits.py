"""Per-guild upload limit resolution.

Discord's attachment size limit depends on the server's boost tier, so a single
hardcoded ceiling either wastes headroom on a boosted server or overshoots on an
unboosted one. discord.py exposes the real value as Guild.filesize_limit:

    tier 0/1  ->  10 MiB
    tier 2    ->  50 MiB
    tier 3    -> 100 MiB

Resolving it per message means the same bot can serve servers on different
tiers, and only re-encodes when that specific server actually requires it.
"""

import logging
from typing import Any, Optional

import config

logger = logging.getLogger(__name__)


def resolve_upload_limit(guild: Optional[Any]) -> int:
    """
    Work out the largest file this guild will accept, in bytes.

    Args:
        guild: The discord.Guild the message came from (may be None)

    Returns:
        The usable upload ceiling in bytes, with headroom subtracted
    """
    # An explicit override wins, for operators who want a smaller cap than the
    # server technically allows (bandwidth, storage, taste).
    if config.MAX_FILE_SIZE_OVERRIDE > 0:
        return config.MAX_FILE_SIZE_OVERRIDE

    reported = getattr(guild, 'filesize_limit', None)

    if not isinstance(reported, int) or reported <= 0:
        # No guild context, or a discord.py version without the attribute
        logger.debug("No guild filesize_limit available, using fallback")
        reported = config.MAX_FILE_SIZE_FALLBACK

    # The limit applies to the whole request, and the embed JSON plus multipart
    # boundaries ride along with the file, so don't aim at the exact ceiling.
    usable = reported - config.UPLOAD_SIZE_HEADROOM

    return max(1, usable)
