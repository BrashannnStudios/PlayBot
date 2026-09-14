import motor.motor_asyncio
from config import MONGO_URI

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["play_big_studios"]

welcome_config = db["welcome_config"]
warns_collection = db["warns"]
notes_collection = db["notes"]
mutes_collection = db["mutes"]
tempbans_collection = db["tempbans"]
counters_collection = db["counters"]


async def get_next_id(guild_id: int, key: str) -> int:
    """
    Returns an incrementing per-guild counter, used for warn-id / note-id.
    """
    result = await counters_collection.find_one_and_update(
        {"guild_id": guild_id, "key": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,
    )
    return result["value"]


async def get_welcome_config(guild_id: int):
    return await welcome_config.find_one({"guild_id": guild_id})


async def set_welcome_config(guild_id: int, data: dict):
    await welcome_config.update_one(
        {"guild_id": guild_id},
        {"$set": data},
        upsert=True,
    )
