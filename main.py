import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持全服/频道定向清理的 Discord 工具", "1.7.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。
        用法: /clean params: [数量] [@用户] [server]
        - 默认只清当前频道。加入 'server' 或 '全服' 关键字可跨频道清理指定用户的消息。
        """
        # 1. 获取 Discord 原生对象 (修复 AttributeError)
        try:
            raw_msg = event.platform_event.raw_event 
            if not isinstance(raw_msg, discord.Message):
                yield event.plain_result("❌ 错误：此指令仅支持在 Discord 使用。")
                return
        except Exception:
            yield event.plain_result("❌ 无法获取 Discord 事件上下文。")
            return

        input_str = params.strip().lower()
        guild = raw_msg.guild
        current_channel = raw_msg.channel

        # 2. 权限预检
        if not (raw_msg.author.guild_permissions.manage_messages or raw_msg.author.guild_permissions.administrator):
            yield event.plain_result("❌ 你没有“管理消息”权限。")
            return

        # 3. 智能解析参数
        # 数量：匹配 1-3 位数字，默认 5
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5

        # 用户 ID：匹配 17-20 位长数字
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 范围判断
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # 4. 执行清理逻辑
        try:
            # 检查函数：如果是定向删人，判断 ID；否则全删
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True # 没指定人就全删

            total_deleted = 0

            if is_server_wide and target_user_id:
                # 模式 A: 全服清理特定用户 (为了安全和性能，限制每个频道扫描深度)
                status_msg = yield event.plain_result(f"🔍 正在全服搜索并清理用户 <@{target_user_id}> 的消息...")
                
                for ch in guild.text_channels:
                    try:
                        # 跨频道清理建议 limit 不要太大，防止触发速率限制
                        deleted = await ch.purge(limit=100, check=check_func)
                        total_deleted += len(deleted)
                    except discord.Forbidden:
                        continue # 跳过没权限的频道
                
                yield event.plain_result(f"✅ 全服清理完成！共清理了 <@{target_user_id}> 的 {total_deleted} 条消息。")

            else:
                # 模式 B: 当前频道清理
                # 如果是清理所有人，count+1 是为了包含指令本身；如果是删特定人，通常不需要+1
                scan_limit = count if target_user_id else count + 1
                deleted = await current_channel.purge(limit=scan_limit, check=check_func)
                
                name = f"用户 <@{target_user_id}>" if target_user_id else "最近"
                yield event.plain_result(f"🧹 已清理 {name} 的 {len(deleted)} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人权限不足，请检查“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 运行出错: {e}")
