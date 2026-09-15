import random
import time
from typing import List

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .messages import FACTIONS
from .model import random_model_text
from .utils import format_duration


@register(
    "astrbot_plugin_jinyan_ccb",
    "Ni-ShuWu",
    "群成员被禁言时自动发送嘲讽消息",
    "v2.4.1",
)
class JinyanCCB(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._recent_events: dict[tuple[str, str, str], float] = {}

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

    def _save_blacklist(self, groups: List[str]) -> bool:
        """将黑名单写入 AstrBot 插件配置并持久化。"""
        try:
            self.config["blacklist_groups"] = groups
            self.config.save_config()
        except Exception as e:
            logger.error(f"保存禁言嘲讽黑名单失败：{e}")
            return False
        return True

    def _add_to_blacklist(self, group_id: int) -> bool:
        gid = str(group_id)
        current = self._get_blacklist()
        if gid in current:
            return False
        current.append(gid)
        return self._save_blacklist(current)

    def _remove_from_blacklist(self, group_id: int) -> bool:
        gid = str(group_id)
        current = self._get_blacklist()
        if gid not in current:
            return False
        current.remove(gid)
        return self._save_blacklist(current)

    def _is_duplicate_event(self, group_id: object, user_id: object, operator_id: object) -> bool:
        """在短时间内过滤适配器重复投递的同一禁言事件。"""
        now = time.monotonic()
        key = (str(group_id), str(user_id), str(operator_id))
        self._recent_events = {
            event_key: timestamp
            for event_key, timestamp in self._recent_events.items()
            if now - timestamp < 10
        }
        if key in self._recent_events:
            return True
        self._recent_events[key] = now
        return False

    def _get_custom_messages(self) -> List[str]:
        """读取自定义文案，兼容多行文本与列表两种配置形态。"""
        raw = self.config.get("custom_messages", "") or ""
        if isinstance(raw, list):
            lines = [str(item) for item in raw]
        else:
            lines = str(raw).splitlines()
        result: List[str] = []
        seen: set[str] = set()
        for line in lines:
            text = line.strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    def _build_candidates(self) -> List[str]:
        """根据文案来源模式返回本次可用的文案候选池。"""
        mode = self.config.get("custom_mode", "builtin")
        if mode not in ("builtin", "custom", "mixed"):
            logger.warning(f"未知的自定义文案模式「{mode}」，已按内置文案处理")
            mode = "builtin"

        candidates: List[str] = []
        if mode in ("builtin", "mixed"):
            for name in FACTIONS:
                if self.config.get(f"enable_{name}", True):
                    candidates.extend(FACTIONS[name])
        if mode in ("custom", "mixed"):
            custom = self._get_custom_messages()
            if mode == "custom" and not custom:
                logger.warning("已选择「仅自定义文案」但未配置 custom_messages，本次回退为内置文案")
                for name in FACTIONS:
                    if self.config.get(f"enable_{name}", True):
                        candidates.extend(FACTIONS[name])
            else:
                candidates.extend(custom)
        return candidates

    @staticmethod
    def _format_message(template: str, user: str, admin: str, duration: str) -> str:
        """安全替换占位符，避免自定义文案中的花括号导致格式化异常。"""
        text = template
        for key, value in (
            ("user", user),
            ("admin", admin),
            ("duration", duration),
            ("model", random_model_text()),
        ):
            text = text.replace("{" + key + "}", value)
        return text

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_event(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return

        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_ban":
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        operator_id = raw.get("operator_id")
        if str(user_id) == "all":
            return
        try:
            group_id_int = int(group_id)
            user_id_int = int(user_id)
            operator_id_int = int(operator_id)
            duration = int(raw.get("duration", 0))
        except (TypeError, ValueError):
            logger.warning(f"忽略字段异常的禁言事件：{raw}")
            return

        if str(group_id) in self._get_blacklist():
            return

        sub_type = raw.get("sub_type", "")

        if sub_type != "ban" or duration <= 0:
            return
        if self._is_duplicate_event(group_id, user_id, operator_id):
            return

        user_name = str(user_id)
        try:
            info = await event.bot.get_stranger_info(user_id=user_id_int)
            if info and isinstance(info.get("nickname"), str) and info["nickname"].strip():
                user_name = info["nickname"].strip()
        except Exception:
            pass

        admin_name = str(operator_id_int) or "管理员"
        try:
            info = await event.bot.get_group_member_info(
                group_id=group_id_int, user_id=operator_id_int
            )
            if info and isinstance(info.get("card"), str) and info["card"].strip():
                admin_name = info["card"].strip()
            elif info and isinstance(info.get("nickname"), str) and info["nickname"].strip():
                admin_name = info["nickname"].strip()
        except Exception:
            pass

        duration_str = format_duration(duration)
        candidates = self._build_candidates()
        if not candidates:
            return
        msg = self._format_message(
            random.choice(candidates), user_name, admin_name, duration_str
        )

        if self.config.get("enable_at_all", False):
            try:
                from astrbot.api.message_components import At

                chain = [At(qq=user_id_int), event.plain_result(" " + msg)]
                await event.send(event.chain_result(chain))
                return
            except Exception as e:
                logger.warning(f"@用户失败，降级为普通消息：{e}")

        try:
            await event.send(event.plain_result(msg))
        except Exception as e:
            logger.warning(f"发送禁言嘲讽消息失败：{e}")

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
        cmd_group_id = None
        if len(parts) > 2:
            try:
                cmd_group_id = int(parts[2])
            except ValueError:
                yield event.plain_result("群号必须是数字")
                return

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
                if str(cmd_group_id) not in self._get_blacklist():
                    yield event.plain_result("黑名单保存失败，请查看日志")
                    return
                yield event.plain_result(f"群 {cmd_group_id} 已在黑名单中")
                return
            yield event.plain_result(
                f"已将群 {cmd_group_id} 加入黑名单（已同步写入 AstrBot 插件配置）"
            )

        elif action == "remove" and cmd_group_id:
            if not self._remove_from_blacklist(cmd_group_id):
                if str(cmd_group_id) in self._get_blacklist():
                    yield event.plain_result("黑名单保存失败，请查看日志")
                    return
                yield event.plain_result(f"群 {cmd_group_id} 不在黑名单中")
                return
            yield event.plain_result(
                f"已将群 {cmd_group_id} 移出黑名单（已同步写入 AstrBot 插件配置）"
            )

        else:
            yield event.plain_result("未知操作，可用：add / remove / list")

    async def terminate(self):
        logger.info("禁言嘲讽插件已卸载")
