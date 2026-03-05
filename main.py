import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持智能解析与多维清理的 Discord 消息工具", "1.8.5")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。
        用法示例: 
        /clean params: 10              (清理最近10条)
        /clean params: @用户 50        (清理该用户最近50条)
        /clean params: @用户 100 server (全服清理该用户)
        """
        # --- 1. 核心修复：多层级探测 Discord 对象 ---
        p_event = getattr(event, 'platform_event', None)
        raw_obj = None
        
        if p_event:
            # 依次探测：raw_obj (新版标准) -> event (旧版) -> raw_event (特定版本)
            for attr in ['raw_obj', 'event', 'raw_event']:
                val = getattr(p_event, attr, None)
                if isinstance(val, (discord.Message, discord.Interaction)):
                    raw_obj = val
                    break
        
        if not raw_obj:
            # 最后的保底尝试
            raw_obj = getattr(event, 'raw_event', None)

        if not raw_obj:
            yield event.plain_result("❌ 兼容性错误：无法直接访问 Discord 原生对象。")
            return

        # 统一获取频道和执行者
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 环境错误：请在服务器频道内使用此指令。")
            return

        # --- 2. 权限检查 ---
        if author and hasattr(author, 'guild_permissions'):
            if not (author.guild_permissions.manage_messages or author.guild_permissions.administrator):
                yield event.plain_result("❌ 权限不足：你没有“管理消息”权限。")
                return

        # --- 3. 参数解析 ---
        input_str = params.strip().lower()
        
        # 提取数量: 1-3位数字
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5

        # 提取用户ID: 17-20位数字
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 提取范围
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 4. 执行清理 ---
        try:
            # 定义过滤逻辑：如果指定了人，就只删那个人的
            def check_logic(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                # 场景一：全服只清理某个人的消息
                yield event.plain_result(f"🔍 正在全服寻找 <@{target_user_id}> 的消息进行清理...")
                total_deleted = 0
                for ch in guild.text_channels:
                    try:
                        # 跨频道建议限制单频道扫描量
                        deleted = await ch.purge(limit=100, check=check_logic)
                        total_deleted += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成，共移除 <@{target_user_id}> 的 {total_deleted} 条消息。")

            else:
                # 场景二：当前频道清理（特定人或所有人）
                # 如果没指定人(全删)，limit+1 删掉指令本身；如果指定了人，则精准寻找
                scan_limit = count if target_user_id else count + 1
                deleted = await channel.purge(limit=scan_limit, check=check_logic)
                
                who = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                # 排除指令本身的计数
                actual_num = len(deleted) if target_user_id else max(0, len(deleted) - 1)
                yield event.plain_result(f"🧹 已成功清理 {who} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人权限不足：请确保机器人有“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 运行异常: {str(e)}")
