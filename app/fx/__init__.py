"""FX rate provider abstraction: a pluggable, vendor-neutral currency layer."""
from app.config import settings
from app.fx.base import FXRateProvider
from app.fx.frankfurter import FrankfurterFXProvider


def get_fx_provider() -> FXRateProvider:
    """Factory: returns the configured FX provider.

    Defaults to the free Frankfurter/ECB source. Set FX_PROVIDER=oanda (plus
    OANDA_API_KEY) in the environment to switch to OANDA without touching
    any reconciliation code.
    """
    if settings.fx_provider == "oanda":
        from app.fx.oanda import OandaFXProvider

        return OandaFXProvider()
    return FrankfurterFXProvider()


__all__ = ["FXRateProvider", "FrankfurterFXProvider", "get_fx_provider"]
