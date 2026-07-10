import random
from typing import List

from astrbot.api import logger
from astrbot.api.config import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .messages import MOCK_MESSAGES
from .utils import format_duration


@register(
    "astrbot_plugin_jinyan_ccb",
    "Ni-ShuWu",
    "群成员被禁言时自动发送嘲讽消息",
    "v2.1.0",
)
class JinyanCCB(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self):
        logger.info(
            f"禁言嘲讽插件已加载，黑名单群聊数量：{len(self._get_blacklist())}"
        )

    def _get_blacklist(self) -> List[str]:
        raw = self.config.get("blacklist_groups", []) or []
        if not isinstance(raw, list):
            return []
        result: List[str] = []
        for item in raw:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                result.append(s)
        return result

    def _add_to_blacklist(self, group_id: int) -> bool:
        gid = str(group_id)
        current = self._get_blacklist()
        if gid in current:
            return False
        current.append(gid)
        self.config.put("blacklist_groups", current)
        self.config.save()
        return True

    def _remove_from_blacklist(self, group_id: int) -> bool:
        gid = str(group_id)
        current = self._get_blacklist()
        if gid not in current:
            return False
        current.remove(gid)
        self.config.put("blacklist_groups", current)
        self.config.save()
        return True

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_event(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return

        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_ban":
            return

        group_id = raw.get("group_id", 0)
        if str(group_id) in self._get_blacklist():
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

        if self.config.get("enable_at_all", False):
            try:
                from astrbot.api.message_components import At

                chain = [At(qq=int(user_id)), event.plain_result(" " + msg)]
                await event.send(event.chain_result(chain))
                return
            except Exception as e:
                logger.warning(f"@用户失败，降级为普通消息：{e}")

        await event.send(event.plain_result(msg))

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("禁言嘲讽黑名单")
    async def blacklist_cmd(self, event: AstrMessageEvent):
        parts = event.get_message_str().strip().split()
        if len(parts) < 2:
            yield event.plain_result(
                "用法：\n"
                "/禁言嘲讽黑名单 add 123456  - 添加群到黑名单\n"
                "/禁言嘲讽黑名单 remove 123456  - 从黑名单移除\n"
                "/禁言嘲讽黑名单 list  - 查看黑名单\n\n"
                "提示：也可在 AstrBot 后台「插件配置」中直接编辑"
            )
            return

        action = parts[1]
        cmd_group_id = int(parts[2]) if len(parts) > 2 else None

        if action == "list":
            groups = self._get_blacklist()
            if not groups:
                yield event.plain_result("黑名单为空")
                return
            yield event.plain_result(
                "当前黑名单群聊：\n" + "\n".join(groups)
            )

        elif action == "add" and cmd_group_id:
            if not self._add_to_blacklist(cmd_group_id):
                yield event.plain_result(f"群 {cmd_group_id} 已在黑名单中")
                return
            yield event.plain_result(
                f"已将群 {cmd_group_id} 加入黑名单（已同步写入 AstrBot 插件配置）"
            )

        elif action == "remove" and cmd_group_id:
            if not self._remove_from_blacklist(cmd_group_id):
                yield event.plain_result(f"群 {cmd_group_id} 不在黑名单中")
                return
            yield event.plain_result(
                f"已将群 {cmd_group_id} 移出黑名单（已同步写入 AstrBot 插件配置）"
            )

        else:
            yield event.plain_result("未知操作，可用：add / remove / list")

    async def terminate(self):
        logger.info("禁言嘲讽插件已卸载")