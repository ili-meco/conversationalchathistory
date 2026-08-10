"""Durable conversational history for Flask applications on Azure App Service."""

from .cosmos_repository import (
    CosmosConversationRepository,
    create_cosmos_repository,
)
from .models import ConversationRecord, FeedbackRecord, MessageRecord
from .repository import (
    ConversationNotFoundError,
    ConversationRepository,
    InvalidFeedbackTargetError,
)

__all__ = [
    "ConversationNotFoundError",
    "ConversationRecord",
    "ConversationRepository",
    "CosmosConversationRepository",
    "FeedbackRecord",
    "InvalidFeedbackTargetError",
    "MessageRecord",
    "create_cosmos_repository",
]