import asyncio
import logging
import time

from ..repository import DeltaRepository, RepositoryError


logger = logging.getLogger(__name__)

CAMPAIGN_TICK_SECONDS = 45.0


class CampaignService:
    """Turns due campaigns into broadcast rows for the existing delivery worker."""

    def __init__(
        self,
        repository: DeltaRepository,
        *,
        interval_seconds: float = CAMPAIGN_TICK_SECONDS,
        batch_limit: int = 10,
    ) -> None:
        self.repository = repository
        self.interval_seconds = float(interval_seconds)
        self.batch_limit = int(batch_limit)

    async def tick(self) -> int:
        due = await self.repository.claim_due_campaigns(
            int(time.time()), limit=self.batch_limit
        )
        sent = 0
        for campaign in due:
            campaign_id = int(campaign["id"])
            try:
                result = await self.repository.dispatch_campaign(campaign_id)
            except asyncio.CancelledError:
                raise
            except RepositoryError as exc:
                # The slot is already advanced, so a broken campaign cannot
                # block the ones behind it in this batch.
                logger.warning("Campaign dispatch rejected: campaign=%s %s", campaign_id, exc)
                continue
            if result.get("broadcast_id"):
                sent += 1
            else:
                logger.info(
                    "Campaign skipped: campaign=%s reason=%s",
                    campaign_id,
                    result.get("reason"),
                )
        return sent

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop_event = asyncio.Event() if stop_event is None else stop_event
        while not stop_event.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Campaign tick failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
