import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "带多重降级机制的 Discord 清理工具", "3.0.0")
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
        
        # ==========================================
        # 核心环节：多重回退机制获取 Discord 对象
        # ==========================================
        
        # 策略 1: 尝试 AstrBot 官方标准路径 (最常见)
        try:
            raw_obj = event.message_obj.raw_message
            if isinstance(raw_obj, (discord.Message, discord.Interaction)):
                channel = getattr(raw_obj, 'channel', None)
                guild = getattr(raw_obj, 'guild', None)
                author = getattr(raw_obj, 'author', getattr(raw_obj, 'user', None))
        except Exception:
            raw_obj = None

        # 策略 2: 尝试从 platform_event 中遍历获取 (兼容旧版或特殊分支)
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

        # 策略 3: 参考 wyf9 做法，直接调用 AstrBot 底层 Client 强制拉取 (终极兜底)
        if not channel:
            try:
                # 尝试获取 discord.Client 实例
                bot_instance = getattr(event, 'bot', None)
                client = getattr(bot_instance, 'client', getattr(bot_instance, 'bot', None))
                
                if isinstance(client, discord.Client):
                    # 通过 AstrBot 统一事件获取当前频道 ID
                    channel_id = event.message_obj.group_id or event.message_obj.session_id
                    if channel_id:
                        channel_id = int(channel_id)
                        # 强行获取或拉取频道
                        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
                        if channel:
                            guild = channel.guild
                            # 这种情况下执行者 ID 只能从 AstrBot 基础事件拿
                            author_id = int(event.message_obj.sender.user_id)
                            author = guild.get_member(author_id) or await guild.fetch_member(author_id)
            except Exception as e:
                logger.warning(f"策略 3 失败: {e}")

        # --- 校验获取结果 ---
        if not channel or not guild:
            yield event.plain_result("❌ 终极环境错误：经过 3 轮尝试，仍无法获取 Discord 频道对象。请确认机器人有“读取消息/查看频道”权限。")
            return

        # ==========================================
        # 权限与参数解析环节
        # ==========================================
        
        # 检查权限
        if author:
            perms = channel.permissions_for(author) if hasattr(channel, 'permissions_for') else getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 你没有“管理消息”权限，无法执行清理。")
                return

        # 解析 params
        input_str = params.strip().lower()
        
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        count = min(count, 100) # 限制单次最大100条以防触发 Discord 限流

        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # ==========================================
        # 执行清理环节 (调用原生 discord.py API)
        # ==========================================
        try:
            # 过滤函数
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                yield event.plain_result(f"🔍 正在全服扫描并清理 <@{target_user_id}> 的消息...")
                total_deleted = 0
                for ch in guild.text_channels:
                    # 检查机器人自身是否有权限删这个频道的图
                    if ch.permissions_for(guild.me).manage_messages:
                        try:
                            deleted = await ch.purge(limit=100, check=check_func)
                            total_deleted += len(deleted)
                        except discord.HTTPException:
                            continue # 忽略单频道报错，继续下个频道
                yield event.plain_result(f"✅ 全服清理完毕，共移除 {total_deleted} 条。")
            
            else:
                # 频道定向清理
                # 如果没有指定人，数量+1是为了把刚发出的 "/clean" 指令本身也删掉
                limit_val = count if target_user_id else count + 1
                deleted = await channel.purge(limit=limit_val, check=check_func)
                
                actual_num = len(deleted)
                if not target_user_id:
                    actual_num = max(0, actual_num - 1)
                
                target_str = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                yield event.plain_result(f"🧹 当前频道已清理 {target_str} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人的权限不足：请在 Discord 频道设置里给机器人勾选“管理消息”权限。")
        except Exception as e:
            logger.error(f"清理执行失败: {e}")
            yield event.plain_result(f"❌ 清理时发生意外错误: {str(e)}")
