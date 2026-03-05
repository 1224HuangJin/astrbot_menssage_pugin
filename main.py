import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "精准定向的 Discord 消息清理工具", "3.1.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        指令用法: /clean params: [数量] [@用户] [server]
        """
        channel = None
        guild = None
        author = None
        
        # --- 1. 获取底层对象 (使用已成功的兜底机制) ---
        try:
            raw_obj = event.message_obj.raw_message
            if isinstance(raw_obj, (discord.Message, discord.Interaction)):
                channel = getattr(raw_obj, 'channel', None)
                guild = getattr(raw_obj, 'guild', None)
                author = getattr(raw_obj, 'author', getattr(raw_obj, 'user', None))
        except Exception:
            raw_obj = None

        if not channel:
            p_event = getattr(event, 'platform_event', None)
            if p_event:
                for attr_name in ['message', 'interaction', 'event', 'raw_event', 'raw_obj']:
                    try:
                        obj = getattr(p_event, attr_name, None)
                        if isinstance(obj, (discord.Message, discord.Interaction)):
                            channel = getattr(obj, 'channel', None)
                            guild = getattr(obj, 'guild', None)
                            author = getattr(obj, 'author', getattr(obj, 'user', None))
                            break
                    except Exception:
                        continue

        if not channel:
            try:
                bot_instance = getattr(event, 'bot', None)
                client = getattr(bot_instance, 'client', getattr(bot_instance, 'bot', None))
                if isinstance(client, discord.Client):
                    channel_id = event.message_obj.group_id or event.message_obj.session_id
                    if channel_id:
                        channel_id = int(channel_id)
                        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
                        if channel:
                            guild = channel.guild
                            author_id = int(event.message_obj.sender.user_id)
                            author = guild.get_member(author_id) or await guild.fetch_member(author_id)
            except Exception:
                pass

        if not channel or not guild:
            yield event.plain_result("❌ 发生意外：无法获取频道对象。")
            return

        # --- 2. 解析参数 ---
        input_str = params.strip().lower()
        
        # 数量：默认 5，最大 100
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        count = min(count, 100) 

        # 提取目标用户 ID
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 校验：如果输入了 @ 但没提取到 ID，说明没正确提及
        if '@' in input_str and not target_user_id:
            yield event.plain_result("❌ 无法识别对象！请确保你在指令中 **真实地 @了那个人**（蓝色高亮字体），而不是手动打字输入名字。")
            return

        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 3. 执行精准清理逻辑 ---
        try:
            # 核心修复：引入状态计数器，确保删够指定数量
            match_count = 0
            def check_func(m):
                nonlocal match_count
                if target_user_id:
                    # 如果找到了对应的人
                    if m.author.id == target_user_id:
                        if match_count < count:
                            match_count += 1
                            return True
                    return False
                return True # 没指定人，删所有

            if is_server_wide and target_user_id:
                yield event.plain_result(f"🔍 正在全服搜寻并清理 <@{target_user_id}> 的 {count} 条消息...")
                total_deleted = 0
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).manage_messages:
                        try:
                            # 深度扫描每个频道 100 条历史
                            deleted = await ch.purge(limit=100, check=check_func)
                            total_deleted += len(deleted)
                            if match_count >= count:
                                break # 已经删够数量，停止全服搜索
                        except discord.HTTPException:
                            continue
                yield event.plain_result(f"✅ 全服清理完毕，共精准移除 <@{target_user_id}> 的 {total_deleted} 条消息。")
            
            else:
                # 频道定向清理
                # 如果指定了人，扫描深度扩大到 100（往上翻找历史），直到找齐对应数量
                # 如果没指定人，只需要扫描并删除 count + 1 条
                scan_depth = 100 if target_user_id else count + 1
                deleted = await channel.purge(limit=scan_depth, check=check_func)
                
                # 计算实际删除数量 (剔除指令本身)
                actual_num = len(deleted)
                if not target_user_id:
                    actual_num = max(0, actual_num - 1)
                
                target_str = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                yield event.plain_result(f"🧹 当前频道已精准清理 {target_str} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人的权限不足，请赋予“管理消息”权限。")
        except Exception as e:
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 意外错误: {str(e)}")
