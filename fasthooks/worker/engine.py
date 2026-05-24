import asyncio
import logging
from typing import Optional

import typer

from fasthooks.worker.dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)
app = typer.Typer(help="Fasthooks webhook delivery sidecar engine.")


class FasthooksEngine:
    """Main execution engine for the webhook delivery sidecar.
    
    Consumes events from a backend and dispatches them via a dispatcher.
    """

    def __init__(
        self,
        backend,
        store,
        signing_secret: str,
        max_concurrency: int = 100,
    ) -> None:
        """Initialize the engine.

        Args:
            backend: Backend instance that implements `consume()` and `ack(event_id)`.
            store: Store instance for webhook subscriptions.
            signing_secret: Secret for signing webhook payloads.
            max_concurrency: Maximum number of concurrent webhook deliveries.
        """
        self.backend = backend
        self.dispatcher = WebhookDispatcher(
            store=store,
            signing_secret=signing_secret,
            max_concurrency=max_concurrency,
        )

    async def run(self):
        """The main execution loop for the sidecar.
        
        Consumes events from the backend, dispatches them, and acknowledges completion.
        """
        logger.info("Starting Fasthooks engine...")
        try:
            async for event in self.backend.consume():
                logger.debug(f"Processing event: {event.event_name}")
                try:
                    await self.dispatcher.broadcast(
                        event_name=event.event_name,
                        payload=event.payload,
                    )
                    await self.backend.ack(event.id)
                    logger.debug(f"Successfully delivered event: {event.event_name}")
                except Exception as e:
                    logger.error(f"Failed to deliver event {event.event_name}: {e}", exc_info=True)
                    # Continue processing other events on error
        finally:
            await self.dispatcher.aclose()
            logger.info("Fasthooks engine stopped.")


@app.command()
def start(
    backend_module: str = typer.Option(
        ..., help="Python module path to backend instance (e.g., 'myapp.backends:redis_backend')"
    ),
    store_module: str = typer.Option(
        ..., help="Python module path to store instance (e.g., 'myapp.stores:sql_store')"
    ),
    signing_secret: str = typer.Option(
        ..., help="Shared secret for signing webhook payloads"
    ),
    max_concurrency: int = typer.Option(
        100, help="Maximum concurrent webhook deliveries"
    ),
    log_level: str = typer.Option(
        "INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
) -> None:
    """Start the Fasthooks webhook delivery sidecar.
    
    Requires module paths to backend and store instances, plus a signing secret.
    """
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Dynamic imports
    try:
        backend = _import_instance(backend_module)
        store = _import_instance(store_module)
    except (ImportError, AttributeError) as e:
        typer.secho(f"Failed to import module: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Create and run engine
    engine = FasthooksEngine(
        backend=backend,
        store=store,
        signing_secret=signing_secret,
        max_concurrency=max_concurrency,
    )

    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal; shutting down...")


def _import_instance(module_path: str):
    """Dynamically import and return an instance from a module path.
    
    Args:
        module_path: Path in format 'module.submodule:instance_name'.
    
    Returns:
        The imported instance.
    
    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the instance is not found.
    """
    if ":" not in module_path:
        raise ImportError(
            f"Invalid module path: {module_path}. Expected format 'module:instance'"
        )

    module_name, instance_name = module_path.rsplit(":", 1)

    try:
        module = __import__(module_name, fromlist=[instance_name])
        return getattr(module, instance_name)
    except ImportError as e:
        raise ImportError(f"Cannot import module '{module_name}': {e}") from e
    except AttributeError as e:
        raise AttributeError(
            f"Instance '{instance_name}' not found in module '{module_name}': {e}"
        ) from e


def main():
    """Entry point for the CLI."""
    app()