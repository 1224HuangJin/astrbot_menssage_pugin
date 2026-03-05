import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持智能解析与多维清理的 Discord 消息工具", "1.6.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。
        用法: /clean [数量] [@用户] [范围: server/channel]
        支持自由顺序，例如: /clean params: <@1471...244> 100
        """
        # 1. 获取原始消息内容进行解析
        # 即使输入了 params:，我们直接取整段参数字符串
        input_str = params.strip() if params else ""
        
        # 2. 获取 Discord 底层对象
        raw_msg = event.raw_event
        guild = getattr(raw_msg, 'guild', None)
        current_channel = getattr(raw_msg, 'channel', None)

        if not current_channel:
            yield event.plain_result("❌ 无法定位频道。请确保在 Discord 服务器频道内使用。")
            return

        # 3. 权限检查 (参考 wyf9)
        try:
            author = getattr(raw_msg, 'author', None)
            if author and hasattr(author, 'guild_permissions'):
                # 必须拥有管理消息权限
                if not (author.guild_permissions.manage_messages or author.guild_permissions.administrator):
                    yield event.plain_result("❌ 权限不足：你没有“管理消息”权限。")
                    return
        except Exception:
            pass # 无法读取权限时尝试继续，由 purge 的 Forbidden 异常处理

        # 4. 智能解析参数 (自由度核心)
        # 提取数量: 匹配 1-3 位数字
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5 # 没写默认删 5 条

        # 提取用户 ID: 匹配 17-20 位长数字 (Mention 或 纯 ID)
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = user_id_match.group(1) if user_id_match else None

        # 提取清理范围: 默认 channel，包含 server 关键字则切换
        scope = "server" if "server" in input_str.lower() else "channel"

        try:
            # 5. 执行清理逻辑 (参考 wyf9)
            target_channels = [current_channel]
            if scope == "server" and guild:
                target_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]

            checked_messages = []
            
            # 逻辑：如果指定了人，扫描历史找到那个人的消息
            if target_user_id:
                for ch in target_channels:
                    try:
                        # 扫描最近的 100 条消息以寻找目标用户的消息
                        async for msg in ch.history(limit=100):
                            if str(msg.author.id) == target_user_id:
                                checked_messages.append(msg)
                                if len(checked_messages) >= count: break
                    except: continue # 忽略无权限访问的频道
            
            # 执行物理删除
            if target_user_id:
                if not checked_messages:
                    yield event.plain_result(f"🧹 未在指定范围内找到用户 <@{target_user_id}> 的消息。")
                    return
                
                # 参考 wyf9 批量删除逻辑
                # Discord API 限制单次删除上限为 100
                await current_channel.delete_messages(checked_messages[:count])
                yield event.plain_result(f"🧹 已清理用户 <@{target_user_id}> 的 {len(checked_messages[:count])} 条消息。")
            
            else:
                # 普通清理模式 (所有人的消息)
                deleted = await current_channel.purge(limit=count + 1)
                yield event.plain_result(f"🧹 已成功清理最近的 {max(0, len(deleted)-1)} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 失败：机器人缺少“管理消息”权限。")
        except Exception as e:
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 清理过程发生错误: {e}")
