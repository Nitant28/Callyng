from fastapi import APIRouter

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


@router.post("/messages")
async def receive_whatsapp_message(data: dict):
    print("WhatsApp data received:", data)

    return {
        "success": True,
        "received": data,
    }

    