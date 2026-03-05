import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持多参数的 Discord 消息清理工具", "1.4.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, count: int = 5, user_mention: str = None, scope: str = "channel"):
        """
        清理指令。
        用法: 
        /clean [数量] [用户] [范围:channel/server]
        示例:
        /clean 10 - 清理当前频道 10 条消息
        /clean 20 @某人 - 清理当前频道该用户的 20 条消息
        /clean 50 @某人 server - 清理全服务器该用户的 50 条消息
        """
        
        # 1. 获取底层对象
        raw_msg = event.raw_event
        guild = getattr(raw_msg, 'guild', None)
        current_channel = getattr(raw_msg, 'channel', None)

        if not current_channel:
            yield event.plain_result("❌ 错误：无法获取频道上下文，请在服务器频道中使用。")
            return

        # 权限简单校验：尝试获取权限对象，失败则跳过（防止报错），靠 purge 自身的权限捕获
        try:
            author = getattr(raw_msg, 'author', None)
            if author and hasattr(author, 'guild_permissions'):
                if not (author.guild_permissions.manage_messages or author.guild_permissions.administrator):
                    yield event.plain_result("❌ 权限不足：你没有“管理消息”权限。")
                    return
        except: pass

        try:
            # 2. 确定目标频道列表 (根据参数 scope)
            target_channels = [current_channel]
            if scope.lower() == "server" and guild:
                # 获取服务器所有文本频道
                target_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]

            success_count = 0
            
            # 3. 执行清理逻辑
            if user_mention:
                # --- 定向清理：删除特定人的消息 ---
                target_id = "".join(re.findall(r'\d+', user_mention))
                if not target_id:
                    yield event.plain_result("❌ 无法识别用户。")
                    return

                def is_target(m): return str(m.author.id) == target_id

                for channel in target_channels:
                    # 扫描频道历史
                    deleted = await channel.purge(limit=100, check=is_target)
                    success_count += len(deleted[:count]) # 累加删除数量
                
                scope_text = "当前频道" if scope != "server" else "全服务器"
                yield event.plain_result(f"🧹 已在 {scope_text} 清理 {user_mention} 的 {success_count} 条消息。")

            else:
                # --- 普通清理：删除最近消息 ---
                # 仅在 scope 为 channel 时支持普通清理，防止全服误删
                deleted = await current_channel.purge(limit=count + 1)
                yield event.plain_result(f"🧹 已清理最近的 {max(0, len(deleted)-1)} 条消息。")

        except Exception as e:
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 操作失败：请检查机器人是否有“管理消息”权限。\n错误: {e}")
