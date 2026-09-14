import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI not set")
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[os.getenv("MONGODB_DB", "playbigstudios")]
        
        # Indexes
        await self.db.guild_configs.create_index("guild_id", unique=True)
        await self.db.warnings.create_index([("guild_id", 1), ("user_id", 1)])
        await self.db.notes.create_index([("guild_id", 1), ("user_id", 1)])
        await self.db.applications.create_index([("guild_id", 1), ("user_id", 1), ("position", 1)])
        await self.db.tempbans.create_index([("guild_id", 1), ("user_id", 1)])
        await self.db.tempbans.create_index("expires_at")

    async def close(self):
        if self.client:
            self.client.close()

    # ── Guild Config ──────────────────────────────────────────────────────
    async def get_guild_config(self, guild_id: int) -> dict:
        doc = await self.db.guild_configs.find_one({"guild_id": guild_id})
        if not doc:
            doc = {
                "guild_id": guild_id,
                "welcome": {
                    "enabled": False,
                    "channel_id": None,
                    "message": "Welcome {user} to **{server}**!",
                    "color": 0x5865F2,
                    "image_url": None,
                    "recommended_channels": [],
                    "links": []
                },
                "vacants": {
                    "enabled": False,
                    "channel_id": None,
                    "open": False,
                    "embed": {
                        "title": "Open Positions",
                        "description": "Click a button below to apply.",
                        "color": 0x5865F2,
                        "image_url": None,
                        "footer": "Play Big Studios"
                    },
                    "positions": [],
                    "questions_default": [
                        "Why do you want this position?",
                        "What experience do you have?",
                        "How many hours per week can you dedicate?"
                    ]
                }
            }
            await self.db.guild_configs.insert_one(doc)
        return doc

    async def update_guild_config(self, guild_id: int, data: dict):
        await self.db.guild_configs.update_one(
            {"guild_id": guild_id},
            {"$set": data},
            upsert=True
        )

    # ── Warnings ──────────────────────────────────────────────────────────
    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> str:
        result = await self.db.warnings.insert_one({
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": datetime.utcnow()
        })
        return str(result.inserted_id)

    async def remove_warning(self, guild_id: int, warn_id: str) -> bool:
        from bson import ObjectId
        try:
            res = await self.db.warnings.delete_one({"_id": ObjectId(warn_id), "guild_id": guild_id})
            return res.deleted_count > 0
        except Exception:
            return False

    async def get_warnings(self, guild_id: int, user_id: int) -> list:
        cursor = self.db.warnings.find({"guild_id": guild_id, "user_id": user_id}).sort("timestamp", -1)
        return await cursor.to_list(length=100)

    # ── Notes ─────────────────────────────────────────────────────────────
    async def add_note(self, guild_id: int, user_id: int, moderator_id: int, note: str) -> str:
        result = await self.db.notes.insert_one({
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "note": note,
            "timestamp": datetime.utcnow()
        })
        return str(result.inserted_id)

    async def remove_note(self, guild_id: int, note_id: str) -> bool:
        from bson import ObjectId
        try:
            res = await self.db.notes.delete_one({"_id": ObjectId(note_id), "guild_id": guild_id})
            return res.deleted_count > 0
        except Exception:
            return False

    async def get_notes(self, guild_id: int, user_id: int) -> list:
        cursor = self.db.notes.find({"guild_id": guild_id, "user_id": user_id}).sort("timestamp", -1)
        return await cursor.to_list(length=50)

    # ── Applications ──────────────────────────────────────────────────────
    async def create_application(self, data: dict) -> str:
        result = await self.db.applications.insert_one(data)
        return str(result.inserted_id)

    async def update_application(self, app_id: str, status: str, reviewer_id: int = None):
        from bson import ObjectId
        update = {"status": status}
        if reviewer_id:
            update["reviewer_id"] = reviewer_id
        await self.db.applications.update_one({"_id": ObjectId(app_id)}, {"$set": update})

    # ── Temp bans ─────────────────────────────────────────────────────────
    async def add_tempban(self, guild_id: int, user_id: int, expires_at, reason: str, moderator_id: int):
        await self.db.tempbans.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {
                "expires_at": expires_at,
                "reason": reason,
                "moderator_id": moderator_id
            }},
            upsert=True
        )

    async def remove_tempban(self, guild_id: int, user_id: int):
        await self.db.tempbans.delete_one({"guild_id": guild_id, "user_id": user_id})

    async def get_expired_tempbans(self):
        cursor = self.db.tempbans.find({"expires_at": {"$lte": datetime.utcnow()}})
        return await cursor.to_list(length=100)

db = Database()
