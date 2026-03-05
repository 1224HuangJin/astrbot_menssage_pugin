import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持智能参数解析的 Discord 清理工具", "1.5.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, *args):
        """
        清理指令。
        用法: /clean params: <@用户> [数量] [范围]
        支持无序输入，例如: /clean 100 @某人
        """
        # 1. 将所有输入参数合并成一个字符串进行解析，解决 "params:" 导致的位移问题
        full_params = " ".join(args)
        
        # 2. 权限校验 (简单校验)
        raw_msg = event.raw_event
        try:
            author = getattr(raw_msg, 'author', None)
            if author and hasattr(author, 'guild_permissions'):
                if not (author.guild_permissions.manage_messages or author.guild_permissions.administrator):
                    yield event.plain_result("❌ 权限不足：你需要“管理消息”权限。")
                    return
        except: pass

        # 3. 智能解析参数
        # 提取数量 (寻找纯数字)
        count_match = re.search(r'\b\d{1,3}\b', full_params)
        count = int(count_match.group()) if count_match else 5 # 默认 5 条
        
        # 提取用户 ID (寻找 Mention 格式或 17-20 位长数字)
        user_id_match = re.search(r'(\d{17,20})', full_params)
        target_user_id = user_id_match.group() if user_id_match else None
        
        # 提取范围 (检查是否包含 server 关键字)
        scope = "server" if "server" in full_params.lower() else "channel"

        # 4. 获取频道对象
        channel = getattr(raw_msg, 'channel', None)
        if not channel:
            yield event.plain_result("❌ 错误：无法定位 Discord 频道。")
            return

        try:
            if target_user_id:
                # --- 定向清理：只删除该用户的消息 ---
                def is_target(m): return str(m.author.id) == target_user_id

                if scope == "server":
                    # 全服务器清理逻辑 (参考 wyf9 [1-3])
                    guild = raw_msg.guild
                    total_deleted = 0
                    text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
                    for ch in text_channels:
                        try:
                            deleted = await ch.purge(limit=100, check=is_target)
                            total_deleted += len(deleted[:count])
                        except: continue
                    yield event.plain_result(f"🧹 已在全服务器清理用户 <@{target_user_id}> 的 {total_deleted} 条消息。")
                else:
                    # 当前频道清理
                    deleted = await channel.purge(limit=100, check=is_target)
                    actual_deleted = deleted[:count]
                    yield event.plain_result(f"🧹 已在当前频道清理用户 <@{target_user_id}> 的 {len(actual_deleted)} 条消息。")
            
            else:
                # --- 普通清理：删除最近的消息 ---
                # limit + 1 是为了包含指令本身
                deleted = await channel.purge(limit=count + 1)
                yield event.plain_result(f"🧹 已清理最近的 {max(0, len(deleted)-1)} 条消息。")

        except Exception as e:
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 失败：请确认机器人拥有“管理消息”权限。\n错误: {e}")
