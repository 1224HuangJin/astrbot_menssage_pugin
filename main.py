import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "适配 Slash Command 的消息清理工具", "2.5.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 获取 Discord 交互对象 ---
        # 在 AstrBot 中，Discord 平台的底层事件通常存放在这里
        p_event = getattr(event, 'platform_event', None)
        # 尝试从 platform_event 中寻找 'event' 属性 (这是 discord.py 的原生 Interaction 或 Message)
        raw_obj = getattr(p_event, 'event', None) 
        
        # 如果还是拿不到，尝试直接获取 message_obj
        if not raw_obj:
            raw_obj = event.message_obj

        if not raw_obj:
            yield event.plain_result("❌ 错误：无法捕获 Discord 交互对象，请确认在 Discord 中使用。")
            return

        # --- 2. 核心：从 Interaction/Message 中提取环境 ---
        # Discord 的 Interaction 对象直接包含 guild 和 channel
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        # 执行者：Interaction 用 user, Message 用 author
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 无法确定位置。请确保机器人在该频道有“查看频道”权限。")
            return

        # --- 3. 权限检查 (参考 wyf9) ---
        if author:
            # 检查是否有管理消息的权限
            perms = channel.permissions_for(author) if hasattr(channel, 'permissions_for') else getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 你没有“管理消息”权限，无法指挥我。")
                return

        # --- 4. 智能解析单个参数 params ---
        input_str = params.strip().lower()
        
        # 提取数字 (1-100)
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        count = min(count, 100) # Discord purge 建议单次不超过 100

        # 提取用户 ID (支持 <@123...> 或 纯数字)
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 范围判断
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 5. 执行清理逻辑 ---
        try:
            # 定义过滤规则：如果指定了人，就只删那个人的
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                yield event.plain_result(f"🔍 启动全服清理：正在各频道搜寻 <@{target_user_id}> 的消息...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        # 检查机器人对该频道是否有权限
                        if ch.permissions_for(guild.me).manage_messages:
                            deleted = await ch.purge(limit=100, check=check_func)
                            total += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成：共移除 {total} 条。")
            
            else:
                # 频道清理模式
                # 如果是普通清理，需要多算 1 条以包含用户发送的指令消息（如果是消息触发的话）
                # 如果是 Slash Command，则不需要 +1
                is_interaction = isinstance(raw_obj, discord.Interaction)
                limit_val = count if (target_user_id or is_interaction) else count + 1
                
                deleted = await channel.purge(limit=limit_val, check=check_func)
                
                # 计数显示逻辑
                display_num = len(deleted)
                if not is_interaction and not target_user_id:
                    display_num = max(0, display_num - 1)
                
                target_name = f"<@{target_user_id}> 的" if target_user_id else "最近"
                yield event.plain_result(f"🧹 已清理 {target_name} {display_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 权限不足：请确保机器人在频道中拥有“管理消息”权限。")
        except Exception as e:
            logger.error(f"Discord Clean Error: {e}")
            yield event.plain_result(f"❌ 运行出错了: {str(e)}")
