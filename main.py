import re
import logging
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 获取 AstrBot 日志记录器
logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "提供 Discord 平台的消息清理及特定用户消息删除功能", "1.2.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean_messages(self, event: AstrMessageEvent, count: int = 5, user_mention: str = None):
        """
        清理消息。
        用法: 
        /clean [数量] - (默认清理最近5条)
        /clean [数量] [@用户/用户ID] - 清理特定用户的消息
        """
                # 1. 权限校验模块
        try:
            # 获取发送者（Member 对象）
            author = getattr(event.raw_event, 'author', None)
            if author:
                # 检查是否拥有“管理消息”或“管理员”权限
                perms = author.guild_permissions
                if not (perms.manage_messages or perms.administrator):
                    yield event.plain_result("❌ 权限不足：你必须拥有“管理消息”权限才能使用此指令。")
                    return
            else:
                yield event.plain_result("❌ 错误：无法验证你的权限（可能非私聊环境或底层对象缺失）。")
                return
        except Exception as e:
            logger.error(f"权限检查出错: {e}")
            yield event.plain_result("❌ 权限校验失败，请联系机器人管理员。")
            return
            
        # 1. 获取 Discord 频道对象 (采用你提供的兼容性写法)
        channel = None
        try:
            # 优先从原始事件获取底层的 discord.py 频道对象
            channel = getattr(event.raw_event, 'channel', None)
            
            # 如果直接拿不到，尝试通过适配器获取
            if not channel:
                adapter = event.bot.get_adapter("discord")
                if adapter:
                    client = adapter.client
                    # 通过消息对象中的 group_id 获取频道
                    channel_id = int(event.message_obj.group_id)
                    channel = client.get_channel(channel_id)
        except Exception as e:
            logger.error(f"获取 Discord 频道失败: {e}")
            yield event.plain_result(f"❌ 无法连接到 Discord 频道，请检查环境。")
            return

        if not channel:
            yield event.plain_result("❌ 错误：未能定位到有效的 Discord 频道。")
            return

        try:
            # 2. 逻辑处理：清理特定用户消息 或 全员消息
            if user_mention:
                # --- 定向清理模式 (删除特定一个人的消息) ---
                # 使用正则表达式提取用户 ID (支持 <@123>, <@!123> 或 纯数字 ID)
                target_id = "".join(re.findall(r'\d+', user_mention))
                
                if not target_id:
                    yield event.plain_result("❌ 无法识别的用户标识，请提供有效的 Mention 或 ID。")
                    return

                # 收集要删除的消息列表
                checked_messages = []
                # 扫描最近的 100 条消息 (增加扫描范围以确保能找到该用户的 count 条消息)
                async for msg in channel.history(limit=100):
                    if str(msg.author.id) == target_id:
                        checked_messages.append(msg)
                        # 达到要求的数量就停止收集
                        if len(checked_messages) >= count:
                            break
                
                if not checked_messages:
                    yield event.plain_result(f"🧹 在最近消息中未找到用户 {user_mention} 的消息。")
                    return

                # 执行删除操作
                await channel.delete_messages(checked_messages)
                yield event.plain_result(f"🧹 已成功清理用户 {user_mention} 的最近 {len(checked_messages)} 条消息。")
                
            else:
                # --- 普通清理模式 (清理当前频道所有人的消息) ---
                # limit 为 count + 1 是为了包含 "/clean" 这条指令本身
                deleted = await channel.purge(limit=count + 1)
                
                # 计算实际删除的数量（减去指令本身）
                actual_deleted = max(0, len(deleted) - 1)
                yield event.plain_result(f"🧹 已成功清理最近的 {actual_deleted} 条消息。")

        except Exception as e:
            # 3. 错误处理：通常是由于权限不足 (如缺少 Manage Messages 权限)
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 失败：请确认 Bot 拥有“管理消息”权限。\n错误: {str(e)}")
