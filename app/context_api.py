"""Explicit, account-scoped research preferences; no chat ingestion."""

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import Actor, get_settings, require_actor
from app.context_store import ContextStore, ContextUnavailable, ResearchPreferences

router = APIRouter(prefix="/api/v1/context", tags=["研究偏好"])


@router.get("/preferences")
def read_preferences(actor: Actor = Depends(require_actor), settings=Depends(get_settings)):
    if not settings.openviking_enabled:
        return dict(state="disabled", preferences=None)
    try:
        with ContextStore(settings, actor.id) as store:
            preferences = store.read_preferences()
        return dict(state="ready", preferences=preferences)
    except ContextUnavailable:
        return dict(state="unavailable", preferences=None)


@router.put("/preferences")
def save_preferences(
    payload: ResearchPreferences,
    actor: Actor = Depends(require_actor),
    settings=Depends(get_settings),
):
    try:
        with ContextStore(settings, actor.id) as store:
            store.save_preferences(payload)
        return dict(state="ready", preferences=payload)
    except ContextUnavailable:
        raise HTTPException(503, "研究偏好暂未保存，请稍后重试") from None


@router.delete("/preferences")
def clear_preferences(actor: Actor = Depends(require_actor), settings=Depends(get_settings)):
    try:
        with ContextStore(settings, actor.id) as store:
            store.clear_preferences()
        return dict(state="ready", preferences=None)
    except ContextUnavailable:
        raise HTTPException(503, "研究偏好暂未清除，请稍后重试") from None
