import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持智能解析与多维清理的 Discord 工具", "2.3.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 使用 AstrBot 官方统一接口获取原生对象 ---
        # message_obj 是官方提供的标准属性，会自动映射到 discord.Message
        raw_obj = event.message_obj
        
        # 备选方案：如果 message_obj 为空，尝试从 platform_event.event 获取
        if not raw_obj:
            p_event = getattr(event, 'platform_event', None)
            raw_obj = getattr(p_event, 'event', None)

        if not raw_obj:
            yield event.plain_result("❌ 兼容性错误：无法获取底层 Discord 对象。请检查插件是否在 Discord 环境运行。")
            return

        # --- 2. 获取环境信息 (适配消息和交互) ---
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        # 获取执行者：Slash Command 用 user，普通消息用 author
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 环境错误：无法确定服务器或频道位置。")
            return

        # --- 3. 权限检查 ---
        if author:
            perms = getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 权限不足：你需要“管理消息”权限。")
                return

        # --- 4. 智能解析单参数 (params) ---
        input_str = params.strip().lower()
        
        # 提取数量 (1-3位数字)，默认 5
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5

        # 提取用户 ID (支持 <@123...> 或 纯 ID)
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 范围判断
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 5. 执行清理逻辑 ---
        try:
            # 过滤函数：如果指定了 ID，就只删那个人的消息
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                # 模式 A: 全服清理某人
                yield event.plain_result(f"🔍 正在全服清理 <@{target_user_id}> 的消息...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        # 限制每个频道扫描前 100 条
                        deleted = await ch.purge(limit=100, check=check_func)
                        total += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成：删除了 <@{target_user_id}> 的 {total} 条消息。")
            
            else:
                # 模式 B: 当前频道清理
                # 如果是清理所有人，purge 会包含触发指令的那条，所以我们要多算 1 条
                # 如果是清理特定人，则直接找满 count 条为止
                scan_limit = count if target_user_id else count + 1
                deleted = await channel.purge(limit=scan_limit, check=check_func)
                
                # 计算显示数量
                actual_num = len(deleted)
                if not target_user_id:
                    actual_num = max(0, actual_num - 1) # 减去指令本身
                
                name = f"<@{target_user_id}> 的" if target_user_id else "最近"
                yield event.plain_result(f"🧹 已清理 {name} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人权限不足：请在频道设置中检查“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 运行异常: {str(e)}")
