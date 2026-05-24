from fastapihooks.worker.base_worker import BaseWorker


class BackgroundTaskWorker(BaseWorker):
    """No-op worker for BackgroundTaskBackend.

    BackgroundTaskBackend delivers webhooks inline via FastAPI background tasks,
    so there is no separate worker loop to run. This class exists for API symmetry
    and to provide a clear error when instantiated.
    """

    async def run(self):
        raise RuntimeError(
            "BackgroundTaskBackend does not require a worker. "
            "Events are dispatched inline via FastAPI BackgroundTasks."
        )

    async def shutdown(self):
        # Nothing to clean up for the no-op worker
        return None
