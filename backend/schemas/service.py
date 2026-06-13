"""
TatvaOps service categories and consultant mapping (TatvaOps Enquiry Form).
"""
from __future__ import annotations
from enum import Enum


class ServiceCategory(str, Enum):
    RESIDENTIAL_CONSTRUCTION = "residential_construction"
    HOME_INTERIORS = "home_interiors"
    PAINTING_WATERPROOFING = "painting_waterproofing"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    SOLAR = "solar"
    HOME_AUTOMATION = "home_automation"
    EVENT_MANAGEMENT = "event_management"
    PROPERTY_DEVELOPMENT = "property_development"
    FARM_INFRASTRUCTURE = "farm_infrastructure"
    IRRIGATION_AUTOMATION = "irrigation_automation"


# Display order for WhatsApp / enquiry (1–11)
SERVICE_MENU = [
    (1, ServiceCategory.RESIDENTIAL_CONSTRUCTION, "🏗️ Residential Construction", "Aravind Narayanan"),
    (2, ServiceCategory.HOME_INTERIORS, "🛋️ Interiors", "Aadhya"),
    (3, ServiceCategory.PAINTING_WATERPROOFING, "🖌️ Painting", "Manjunath Gowda"),
    (4, ServiceCategory.ELECTRICAL, "⚡ Electrical Services", "Vivek Shetty"),
    (5, ServiceCategory.PLUMBING, "🔧 Plumbing Services", "Suresh Kumar"),
    (6, ServiceCategory.SOLAR, "☀️ Solar Services", "Kavya Nair"),
    (7, ServiceCategory.EVENT_MANAGEMENT, "🎪 Event Management", "Meera Iyer"),
    (8, ServiceCategory.PROPERTY_DEVELOPMENT, "🏢 Property Development", "Vikram Desai"),
    (9, ServiceCategory.HOME_AUTOMATION, "🏠 Home Automation", "Riya Mehta"),
    (10, ServiceCategory.FARM_INFRASTRUCTURE, "🌾 Farm Infrastructure Setup", "Anil Reddy"),
    (11, ServiceCategory.IRRIGATION_AUTOMATION, "💧 Irrigation Automation", "Deepak Patil"),
]

# Short labels for WhatsApp list rows (max 24 characters)
SERVICE_WHATSAPP_LABELS: dict[ServiceCategory, str] = {
    ServiceCategory.RESIDENTIAL_CONSTRUCTION: "🏗️ Residential Const.",
    ServiceCategory.HOME_INTERIORS: "🛋️ Interiors",
    ServiceCategory.PAINTING_WATERPROOFING: "🖌️ Painting",
    ServiceCategory.ELECTRICAL: "⚡ Electrical",
    ServiceCategory.PLUMBING: "🔧 Plumbing",
    ServiceCategory.SOLAR: "☀️ Solar Services",
    ServiceCategory.EVENT_MANAGEMENT: "🎪 Event Management",
    ServiceCategory.PROPERTY_DEVELOPMENT: "🏢 Property Dev.",
    ServiceCategory.HOME_AUTOMATION: "🏠 Home Automation",
    ServiceCategory.FARM_INFRASTRUCTURE: "🌾 Farm Setup",
    ServiceCategory.IRRIGATION_AUTOMATION: "💧 Irrigation",
}

# Must match Twilio list-picker row count in TWILIO_SERVICE_SELECTION_CONTENT_SID (current template: 6)
WHATSAPP_SERVICE_LIST_ROWS = 6

SERVICE_MORE_VALUE = "__service_more__"
SERVICE_MORE_LABEL = "View more"

CONSULTANT_IDS = {
    ServiceCategory.RESIDENTIAL_CONSTRUCTION: "aravind",
    ServiceCategory.HOME_INTERIORS: "aadhya",
    ServiceCategory.PAINTING_WATERPROOFING: "manjunath",
    ServiceCategory.ELECTRICAL: "vivek",
    ServiceCategory.PLUMBING: "suresh",
    ServiceCategory.SOLAR: "kavya",
    ServiceCategory.HOME_AUTOMATION: "riya",
    ServiceCategory.EVENT_MANAGEMENT: "meera",
    ServiceCategory.PROPERTY_DEVELOPMENT: "vikram",
    ServiceCategory.FARM_INFRASTRUCTURE: "anil",
    ServiceCategory.IRRIGATION_AUTOMATION: "deepak",
}

# TatvaOps MongoDB service _id values (services collection)
SERVICE_MONGO_IDS: dict[ServiceCategory, str] = {
    ServiceCategory.RESIDENTIAL_CONSTRUCTION: "6926b7865c6d9f597ae41693",
    ServiceCategory.HOME_INTERIORS: "6926b1978ba6a3cfc5a191ce",
    ServiceCategory.PAINTING_WATERPROOFING: "6926a8308ba6a3cfc5a19114",
    ServiceCategory.ELECTRICAL: "6982f2e19397ea98d6f9600c",
    ServiceCategory.PLUMBING: "6982f37d9397ea98d6f96019",
    ServiceCategory.SOLAR: "6926a8928ba6a3cfc5a1911b",
    ServiceCategory.EVENT_MANAGEMENT: "6926b4b35c6d9f597ae41670",
    ServiceCategory.PROPERTY_DEVELOPMENT: "6926b24a8ba6a3cfc5a191d5",
    ServiceCategory.HOME_AUTOMATION: "6926a7728ba6a3cfc5a19104",
    ServiceCategory.FARM_INFRASTRUCTURE: "6926b3888ba6a3cfc5a191e6",
    ServiceCategory.IRRIGATION_AUTOMATION: "6926aa018ba6a3cfc5a19122",
}

MONGO_ID_TO_SERVICE: dict[str, ServiceCategory] = {
    mongo_id: category for category, mongo_id in SERVICE_MONGO_IDS.items()
}


def get_service_mongo_id(category: ServiceCategory) -> str:
    return SERVICE_MONGO_IDS[category]


def service_from_mongo_id(mongo_id: str) -> ServiceCategory | None:
    return MONGO_ID_TO_SERVICE.get(mongo_id.strip())
