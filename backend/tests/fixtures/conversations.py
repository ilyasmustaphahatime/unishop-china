"""Synthetic chat worlds: sequential rollback fixtures and exact committed cleanup."""
import base64
from dataclasses import dataclass
from datetime import datetime
import secrets
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.enums import UserRoleType
from app.core.config import settings
from app.models import Category, City, ProductListing, SellerVerification, User, UserProfile, UserRole
from app.models.seller_verification import VerificationStatus


@dataclass
class ChatWorld:
    seller: User
    buyer: User
    outsider: User
    category: Category
    products: list[ProductListing]


def chat_config(**changes):
    """Generate isolated test-only secrets; never read or log production contact keys."""
    return settings.model_copy(update={
        "app_debug": False,
        "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48)),
        "wechat_contact_encryption_key": SecretStr(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()),
        **changes,
    })


def seed_chat_world(db: Session, *, count: int = 3) -> ChatWorld:
    marker = uuid4().hex
    users = [User(email=f"chat-test-{marker}-{index}@example.test", password_hash="unusable",
                  email_verified=True, phone_verified=True) for index in range(3)]
    db.add_all(users)
    db.flush()
    for user in users:
        db.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    city = db.scalar(select(City).where(City.slug == "qingdao"))
    assert city is not None
    seller = users[0]
    db.add(UserProfile(user_id=seller.id, display_name="Synthetic chat seller", city=city.name_en,
                       city_id=city.id, onboarding_completed=True))
    now = datetime.now()
    db.add(SellerVerification(user_id=seller.id, status=VerificationStatus.VERIFIED,
                              submitted_at=now, reviewed_at=now))
    category = Category(slug="chat-test-" + marker[:16], name_en="Synthetic chat", name_zh="测试")
    db.add(category)
    db.flush()
    products = [ProductListing(seller_user_id=seller.id, title=f"Synthetic chat desk {index}",
        description="A synthetic product used only for messaging security tests.", price="32.50",
        currency="CNY", condition="good", status="PUBLISHED", city_id=city.id,
        category_id=category.id, published_at=now) for index in range(count)]
    db.add_all(products)
    db.flush()
    return ChatWorld(seller, users[1], users[2], category, products)


def cleanup_chat_world(db: Session, world: ChatWorld) -> None:
    """Delete only this world's known IDs in dependency order, never table-wide rows."""
    from app.models.conversation import Conversation

    product_ids = [product.id for product in world.products]
    user_ids = [world.seller.id, world.buyer.id, world.outsider.id]
    db.execute(delete(Conversation).where(Conversation.product_listing_id.in_(product_ids),
                                         Conversation.seller_user_id == world.seller.id))
    db.execute(delete(ProductListing).where(ProductListing.id.in_(product_ids),
                                            ProductListing.seller_user_id == world.seller.id))
    db.execute(delete(User).where(User.id.in_(user_ids)))
    db.execute(delete(Category).where(Category.id == world.category.id))
