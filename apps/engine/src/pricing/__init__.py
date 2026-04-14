from src.pricing.types import PricingQuoteRequest, PricingQuoteResponse

__all__ = [
    "get_pricing_quote",
    "PricingQuoteRequest",
    "PricingQuoteResponse",
]


def get_pricing_quote(*args, **kwargs):
    from src.pricing.quote import get_pricing_quote as _fn
    return _fn(*args, **kwargs)
