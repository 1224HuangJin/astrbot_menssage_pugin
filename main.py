import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "全能型 Discord 消息清理工具", "2.0.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 属性雷达：扫描所有可能的 Discord 原生对象 ---
        raw_obj = None
        p_event = getattr(event, 'platform_event', event) # 如果没有 platform_event 就看 event 自己
        
        # 这里的逻辑是：遍历对象的所有属性，寻找类型中包含 'discord' 字样的对象
        for attr_name in dir(p_event):
            if attr_name.startswith('_'): continue
            try:
                attr_value = getattr(p_event, attr_name)
                # 检查这个属性是不是 discord.Message 或 discord.Interaction
                if isinstance(attr_value, (discord.Message, discord.Interaction)):
                    raw_obj = attr_value
                    # logger.info(f"找到 Discord 对象: {attr_name}")
                    break
            except: continue

        # 如果还是找不到，尝试从 AstrBot 的统一接口获取
        if not raw_obj:
            raw_obj = getattr(event, 'message_obj', None)

        if not raw_obj:
            # 最后的最后，如果还是不行，输出一下这个对象到底有哪些属性，方便我们后续排查
            attrs = [a for a in dir(p_event) if not a.startswith('_')]
            yield event.plain_result(f"❌ 兼容性错误：无法定位底层对象。\n当前环境属性: {', '.join(attrs[:10])}...")
            return

        # --- 2. 提取频道、服务器和作者信息 ---
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        # Interaction 用 user, Message 用 author
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 环境错误：无法获取服务器频道信息。")
            return

        # --- 3. 权限预检 ---
        if author:
            perms = getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 权限不足：你没有“管理消息”权限。")
                return

        # --- 4. 智能解析参数 ---
        input_str = params.strip().lower()
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 5. 执行清理逻辑 ---
        try:
            def check_logic(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                yield event.plain_result(f"🔍 启动全服清理：目标 <@{target_user_id}>...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        deleted = await ch.purge(limit=100, check=check_logic)
                        total += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成，共移除 {total} 条消息。")
            else:
                # 模式 B: 当前频道清理
                scan_limit = count if target_user_id else count + 1
                deleted = await channel.purge(limit=scan_limit, check=check_logic)
                
                who = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                display_num = len(deleted) if target_user_id else max(0, len(deleted) - 1)
                yield event.plain_result(f"🧹 已清理 {who} {display_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人缺少“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 运行异常: {str(e)}")
