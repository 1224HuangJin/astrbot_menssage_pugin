import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "支持智能解析与多维清理", "1.7.5")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。
        用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 强力获取 Discord 上下文 ---
        # 尝试从不同的地方挖出 Discord 的原生对象
        p_event = getattr(event, 'platform_event', None)
        raw_event = getattr(p_event, 'raw_event', p_event) # 兼容不同版本的 AstrBot
        
        # 寻找 channel 对象 (不管是 Message 还是 Interaction 都有这个)
        channel = getattr(raw_event, 'channel', None)
        guild = getattr(raw_event, 'guild', None)
        
        # 寻找执行者 (Interaction 用 .user, Message 用 .author)
        author = getattr(raw_event, 'user', getattr(raw_event, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 错误：无法识别 Discord 频道环境。请确保在服务器内使用。")
            return

        # --- 2. 权限检查 ---
        perms = getattr(author, 'guild_permissions', None)
        if perms and not (perms.manage_messages or perms.administrator):
            yield event.plain_result("❌ 权限不足：你需要“管理消息”权限。")
            return

        # --- 3. 智能解析参数 ---
        input_str = params.strip().lower()
        
        # 提取数量 (1-3位数字)，默认 5
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5

        # 提取用户 ID (支持 <@!123...> 或 纯数字)
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None

        # 是否是全服模式
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 4. 执行清理 ---
        try:
            # 定义过滤规则：如果指定了 ID，就只删那个人的
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                # 模式 A: 全服搜寻某人并删除
                yield event.plain_result(f"🔍 正在全服搜索并清理 <@{target_user_id}> 的消息...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        # 全服清理时 limit 不要太高，防止被 Discord 封禁
                        deleted = await ch.purge(limit=50, check=check_func)
                        total += len(deleted)
                    except: continue 
                yield event.plain_result(f"✅ 清理完毕！共删除 <@{target_user_id}> 的 {total} 条消息。")

            else:
                # 模式 B: 当前频道清理 (支持所有人或特定人)
                # 如果是清理所有人，purge 的 limit 设为 count + 1 (包含指令本身)
                scan_limit = count if target_user_id else count + 1
                deleted = await channel.purge(limit=scan_limit, check=check_func)
                
                msg_target = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                # 减去指令本身（如果清理的是所有人的话）
                display_count = len(deleted) if target_user_id else max(0, len(deleted) - 1)
                yield event.plain_result(f"🧹 已清理 {msg_target} {display_count} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 机器人缺少“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean error: {e}")
            yield event.plain_result(f"❌ 运行出错了: {str(e)}")
