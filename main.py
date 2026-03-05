import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "全能型 Discord 消息清理工具", "2.1.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 获取底层对象 ---
        p_event = getattr(event, 'platform_event', None)
        raw_obj = None
        if p_event:
            # 探测优先级：.event (最常用) -> .raw_obj -> .message
            for attr in ['event', 'raw_obj', 'message', 'interaction']:
                val = getattr(p_event, attr, None)
                if val:
                    raw_obj = val
                    break
        
        if not raw_obj:
            raw_obj = getattr(event, 'raw_event', None)

        if not raw_obj:
            yield event.plain_result("❌ 兼容性错误：无法获取 Discord 底层对象。")
            return

        # --- 2. 强力获取 Channel 和 Guild ---
        # 尝试直接获取
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        
        # 如果获取不到，尝试通过 ID 强制从 client 找 (AstrBot 内部路径)
        if not channel or not guild:
            try:
                # 尝试从 p_event 或 raw_obj 找 client (机器人实例)
                client = getattr(p_event, 'client', getattr(raw_obj, 'client', None))
                if client:
                    # 如果能拿到 ID，就强行 fetch
                    c_id = getattr(raw_obj, 'channel_id', None)
                    g_id = getattr(raw_obj, 'guild_id', None)
                    if c_id: channel = client.get_channel(c_id) or await client.fetch_channel(c_id)
                    if g_id: guild = client.get_guild(g_id)
            except:
                pass

        if not channel:
            yield event.plain_result("❌ 环境错误：无法确定当前频道，请重试。")
            return

        # --- 3. 提取执行者与权限检查 ---
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))
        if author:
            # 这里的 perms 检查做了容错，防止 get_member 失败
            perms = getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 权限不足：你需要“管理消息”权限。")
                return

        # --- 4. 解析参数 ---
        input_str = params.strip().lower()
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 5. 执行逻辑 ---
        try:
            def check_logic(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id and guild:
                yield event.plain_result(f"🔍 启动全服清理：目标 <@{target_user_id}>...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        deleted = await ch.purge(limit=100, check=check_logic)
                        total += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成，共移除 {total} 条消息。")
            
            else:
                # 当前频道清理
                # purge 是异步生成器，不需要额外 handle 复杂的 Discord 对象转换
                deleted = await channel.purge(limit=count + 1 if not target_user_id else 100, check=check_logic)
                
                # 计算删除数量：
                # 如果指定了人，删除数就是 len(deleted)
                # 如果没指定人，由于 purge 包含了指令本身，所以需要 -1
                actual_num = len(deleted)
                if not target_user_id:
                    actual_num = max(0, actual_num - 1)
                
                who = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                yield event.plain_result(f"🧹 已成功清理 {who} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人权限不足：请在频道设置中开启“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 运行异常: {str(e)}")
