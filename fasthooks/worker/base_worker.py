from abc import ABC, abstractmethod


class BaseWorker(ABC):
    """Abstract worker contract for fasthooks sidecars."""

    @abstractmethod
    async def run(self):
        """Start the worker loop."""
        raise NotImplementedError

    async def shutdown(self):
        """Optional graceful shutdown hook."""
        # Default is a no-op so implementations can opt-in.
        return None
