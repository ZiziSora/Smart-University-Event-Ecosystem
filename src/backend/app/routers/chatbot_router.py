"""Endpoint chatbox trợ lý AI (dùng ở trang Khám phá)."""
from typing import Optional

from fastapi import APIRouter, Depends
from app.models.user import User

from app.core.auth import get_optional_user
from app.schemas.chatbot import ChatMessageIn, ChatMessageOut
from app.services import chatbot_service

router = APIRouter(prefix="/api/chatbot", tags=["chatbot"])


@router.post("/messages", response_model=ChatMessageOut)
def post_chat_message(
    payload: ChatMessageIn,
    current_user: Optional[User] = Depends(get_optional_user),
) -> ChatMessageOut:
    """Nhận câu hỏi của người dùng, trả về câu trả lời của trợ lý AI.

    Không bắt buộc đăng nhập; nếu có token hợp lệ thì `user_id` được truyền
    xuống service để phục vụ cá nhân hoá về sau.
    """
    user_id = str(current_user.user_id) if current_user else None
    return chatbot_service.answer_chat_message(payload, user_id=user_id)
