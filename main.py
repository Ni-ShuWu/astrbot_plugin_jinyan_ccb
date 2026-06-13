import os
import random

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .blacklist import BlacklistManager
from .messages import MOCK_MESSAGES
from .utils import format_duration


class JinyanCCB(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        data_dir = os.path.dirname(os.path.abspath(__file__))
        self.blacklist = BlacklistManager(data_dir)

    async def initialize(self):
        self.blacklist.load()
        logger.info(f"禁言嘲讽插件已加载，黑名单数量：{len(self.blacklist.groups)}")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_event(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return

        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_ban":
            return

        group_id = raw.get("group_id", 0)
        if self.blacklist.is_blacklisted(group_id):
            return

        sub_type = raw.get("sub_type", "")
        user_id = raw.get("user_id", "")
        duration = raw.get("duration", 0)

        if sub_type != "ban" or duration <= 0 or str(user_id) == "all":
            return

        user_name = str(user_id)
        try:
            info = await event.bot.get_stranger_info(user_id=int(user_id))
            if info and "nickname" in info:
                user_name = info["nickname"]
        except Exception:
            pass

        duration_str = format_duration(duration)
        msg = random.choice(MOCK_MESSAGES).format(
            user=user_name, duration=duration_str
        )

        await event.send(event.plain_result(msg))

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("禁言嘲讽黑名单")
    async def blacklist_cmd(self, event: AstrMessageEvent):
        parts = event.get_message_str().strip().split()
        if len(parts) < 2:
            yield event.plain_result(
                "用法：\n/禁言嘲讽黑名单 add 123456  - 添加群到黑名单\n"
                "/禁言嘲讽黑名单 remove 123456  - 从黑名单移除\n"
                "/禁言嘲讽黑名单 list  - 查看黑名单"
            )
            return

        action = parts[1]
        cmd_group_id = int(parts[2]) if len(parts) > 2 else None

        if action == "list":
            groups = self.blacklist.list()
            if not groups:
                yield event.plain_result("黑名单为空")
                return
            yield event.plain_result(
                "当前黑名单群聊：\n" + "\n".join(str(g) for g in groups)
            )

        elif action == "add" and cmd_group_id:
            if not self.blacklist.add(cmd_group_id):
                yield event.plain_result(f"群 {cmd_group_id} 已在黑名单中")
                return
            yield event.plain_result(f"已将群 {cmd_group_id} 加入黑名单")

        elif action == "remove" and cmd_group_id:
            if not self.blacklist.remove(cmd_group_id):
                yield event.plain_result(f"群 {cmd_group_id} 不在黑名单中")
                return
            yield event.plain_result(f"已将群 {cmd_group_id} 移出黑名单")

        else:
            yield event.plain_result("未知操作，可用：add / remove / list")

    async def terminate(self):
        logger.info("禁言嘲讽插件已卸载")
