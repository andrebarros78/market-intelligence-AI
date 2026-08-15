from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SurfaceCategory(StrEnum):
    ACCOUNT = "account"
    OFFER = "offer"
    PRICING = "pricing"
    CATALOG = "catalog"
    DEMAND = "demand"
    ORDER = "order"
    LOGISTICS = "logistics"
    PROMOTION = "promotion"
    COMMUNICATION = "communication"
    POST_PURCHASE = "post_purchase"
    FINANCIAL = "financial"
    LEADS = "leads"


class SurfaceCaptureMode(StrEnum):
    POLL_SAFE = "poll_safe"
    WEBHOOK_GET_SAFE = "webhook_get_safe"
    DEDICATED_PRIVACY_READER = "dedicated_privacy_reader"
    WEBHOOK_METADATA_ONLY = "webhook_metadata_only"
    DERIVED = "derived"
    DEPRECATED = "deprecated"


@dataclass(frozen=True, slots=True)
class MarketSurface:
    surface_id: str
    label: str
    category: SurfaceCategory
    capture_mode: SurfaceCaptureMode
    notification_topic: str | None = None
    contains_or_may_contain_pii: bool = False
    intelligence_priority: int = 5
    replacement_surface_id: str | None = None
    notes: str = ""


# Registry is intentionally declarative. Unknown topics are not auto-followed; they
# become Sondador discoveries requiring a new explicit low-PII resolver or dedicated
# privacy-aware reader before any resource GET is enabled.
MERCADOLIVRE_SURFACES: tuple[MarketSurface, ...] = (
    MarketSurface("account", "Usuário/conta", SurfaceCategory.ACCOUNT, SurfaceCaptureMode.POLL_SAFE, intelligence_priority=7),
    MarketSurface("items", "Items", SurfaceCategory.OFFER, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="items", intelligence_priority=10),
    MarketSurface("price_suggestion", "Price Suggestion", SurfaceCategory.PRICING, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="price_suggestion", intelligence_priority=10),
    MarketSurface("items_prices", "Items Prices", SurfaceCategory.PRICING, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="items_prices", intelligence_priority=10),
    MarketSurface("item_competition", "Item Competition", SurfaceCategory.CATALOG, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="catalog_item_competition_status", intelligence_priority=10),
    MarketSurface("catalog_suggestions", "Catalog Suggestions", SurfaceCategory.CATALOG, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="catalog_suggestions", intelligence_priority=9),
    MarketSurface("stock_locations", "Stock-Locations", SurfaceCategory.LOGISTICS, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="stock-location", intelligence_priority=9),
    MarketSurface("user_products_families", "User Products Families", SurfaceCategory.CATALOG, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="user-products-families", intelligence_priority=9),
    MarketSurface("questions", "Questions", SurfaceCategory.DEMAND, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, notification_topic="questions", contains_or_may_contain_pii=True, intelligence_priority=10),
    MarketSurface("orders_v2", "Orders_V2", SurfaceCategory.ORDER, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=10),
    MarketSurface("orders_feedback", "Orders Feedback", SurfaceCategory.POST_PURCHASE, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("messages_created", "Messages / Created", SurfaceCategory.COMMUNICATION, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, notification_topic="messages", contains_or_may_contain_pii=True, intelligence_priority=9),
    MarketSurface("messages_read", "Messages / Read", SurfaceCategory.COMMUNICATION, SurfaceCaptureMode.WEBHOOK_METADATA_ONLY, notification_topic="messages", contains_or_may_contain_pii=True, intelligence_priority=7),
    MarketSurface("insurance_messages", "Insurance Messages", SurfaceCategory.COMMUNICATION, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=5),
    MarketSurface("shipments", "Shipments", SurfaceCategory.LOGISTICS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=9),
    MarketSurface("fbm_stock_operations", "FBM Stock Operations", SurfaceCategory.LOGISTICS, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="fbm_stock_operations", intelligence_priority=8),
    MarketSurface("flex_handshakes", "Flex-Handshakes", SurfaceCategory.LOGISTICS, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="flex-handshakes", intelligence_priority=7),
    MarketSurface("public_offers", "Public Offers", SurfaceCategory.PROMOTION, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="public_offers", intelligence_priority=10),
    MarketSurface("public_candidates", "Public Candidates", SurfaceCategory.PROMOTION, SurfaceCaptureMode.WEBHOOK_GET_SAFE, notification_topic="public_candidates", intelligence_priority=10),
    MarketSurface("vis_whatsapp", "VIS Leads / WhatsApp", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("vis_call", "VIS Leads / Call", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("vis_question", "VIS Leads / Question", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("vis_visit_request", "VIS Leads / Visit Request", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=7),
    MarketSurface("vis_contact_request", "VIS Leads / Contact Request", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("vis_reservation", "VIS Leads / Reservation", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("vis_quotation", "VIS Leads / Quotation", SurfaceCategory.LEADS, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=9),
    MarketSurface("legacy_item_quotations", "Items / Quotations (legado)", SurfaceCategory.LEADS, SurfaceCaptureMode.DEPRECATED, intelligence_priority=1, replacement_surface_id="vis_quotation", notes="Fluxo legado descontinuado em 15/05/2026; usar VIS Leads / Quotation."),
    MarketSurface("post_purchase", "Post Purchase", SurfaceCategory.POST_PURCHASE, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("claims", "Claims", SurfaceCategory.POST_PURCHASE, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, notification_topic="claims", contains_or_may_contain_pii=True, intelligence_priority=9),
    MarketSurface("claims_actions", "Claims Actions", SurfaceCategory.POST_PURCHASE, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=8),
    MarketSurface("payments", "Payments", SurfaceCategory.FINANCIAL, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, notification_topic="payments", contains_or_may_contain_pii=True, intelligence_priority=9),
    MarketSurface("invoices", "Invoices", SurfaceCategory.FINANCIAL, SurfaceCaptureMode.DEDICATED_PRIVACY_READER, contains_or_may_contain_pii=True, intelligence_priority=7),
    MarketSurface("leads_credits", "Leads-Credits", SurfaceCategory.LEADS, SurfaceCaptureMode.WEBHOOK_METADATA_ONLY, notification_topic="leads-credits", contains_or_may_contain_pii=True, intelligence_priority=5),
)


_BY_ID = {surface.surface_id: surface for surface in MERCADOLIVRE_SURFACES}
_BY_TOPIC: dict[str, tuple[MarketSurface, ...]] = {}
for _surface in MERCADOLIVRE_SURFACES:
    if _surface.notification_topic:
        _BY_TOPIC[_surface.notification_topic] = (*_BY_TOPIC.get(_surface.notification_topic, ()), _surface)


def all_surfaces() -> tuple[MarketSurface, ...]:
    return MERCADOLIVRE_SURFACES


def surface_by_id(surface_id: str) -> MarketSurface | None:
    return _BY_ID.get(surface_id)


def surfaces_for_topic(topic: str) -> tuple[MarketSurface, ...]:
    return _BY_TOPIC.get(topic.strip().lower(), ())


def is_known_notification_topic(topic: str) -> bool:
    return bool(surfaces_for_topic(topic))
