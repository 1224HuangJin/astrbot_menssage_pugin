import re
import logging
import discord
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "全能型 Discord 消息清理工具", "2.2.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("clean")
    async def clean(self, event: AstrMessageEvent, params: str = ""):
        """
        清理指令。用法: /clean params: [数量] [@用户] [server]
        """
        # --- 1. 【超强探测】不再死磕固定属性，全自动扫描 ---
        raw_obj = None
        
        # 探测列表：检查 event 本身及其内部所有包装层
        search_targets = [event]
        if hasattr(event, 'platform_event'):
            search_targets.append(event.platform_event)
        
        for target in search_targets:
            # 扫描 target 里的所有属性
            for attr in dir(target):
                if attr.startswith('_'): continue
                try:
                    val = getattr(target, attr)
                    # 只要这个属性是 discord 的消息或交互对象，就是我们要找的
                    if isinstance(val, (discord.Message, discord.Interaction)):
                        raw_obj = val
                        break
                except: continue
            if raw_obj: break

        # --- 2. 【报错诊断】如果还是找不到，直接把“内脏”露出来看看 ---
        if not raw_obj:
            p_event = getattr(event, 'platform_event', None)
            debug_info = dir(p_event) if p_event else dir(event)
            yield event.plain_result(f"❌ 兼容性错误：找不到底层对象。\n可用属性: {str(debug_info[:15])}")
            return

        # --- 3. 获取频道、服务器和作者 ---
        # 适配 Slash Command (interaction) 和普通消息 (message)
        channel = getattr(raw_obj, 'channel', None)
        guild = getattr(raw_obj, 'guild', None)
        author = getattr(raw_obj, 'user', getattr(raw_obj, 'author', None))

        if not channel or not guild:
            yield event.plain_result("❌ 环境错误：无法获取服务器/频道。请确保在频道内使用。")
            return

        # --- 4. 权限检查 ---
        if author:
            perms = getattr(author, 'guild_permissions', None)
            if perms and not (perms.manage_messages or perms.administrator):
                yield event.plain_result("❌ 权限不足：你没有“管理消息”权限。")
                return

        # --- 5. 智能解析参数 ---
        input_str = params.strip().lower()
        # 提取数字 (1-3位)
        count_match = re.search(r'\b(\d{1,3})\b', input_str)
        count = int(count_match.group(1)) if count_match else 5
        # 提取用户ID (17-20位数字)
        user_id_match = re.search(r'(\d{17,20})', input_str)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None
        # 范围判断
        is_server_wide = any(k in input_str for k in ["server", "全服", "all"])

        # --- 6. 执行清理逻辑 ---
        try:
            # 过滤逻辑：只删指定人的，或者全删
            def check_func(m):
                if target_user_id:
                    return m.author.id == target_user_id
                return True

            if is_server_wide and target_user_id:
                yield event.plain_result(f"🔍 正在全服清理 <@{target_user_id}> 的消息...")
                total = 0
                for ch in guild.text_channels:
                    try:
                        deleted = await ch.purge(limit=100, check=check_func)
                        total += len(deleted)
                    except: continue
                yield event.plain_result(f"✅ 全服清理完成，共移除 {total} 条。")
            
            else:
                # 普通频道清理
                # 如果没指定人，limit+1 删掉指令本身；如果指定了人，直接按 count 找
                limit_val = count if target_user_id else count + 1
                deleted = await channel.purge(limit=limit_val, check=check_func)
                
                # 计数显示
                actual_num = len(deleted) if target_user_id else max(0, len(deleted) - 1)
                who = f"<@{target_user_id}> 的" if target_user_id else "最近的"
                yield event.plain_result(f"🧹 已成功清理 {who} {actual_num} 条消息。")

        except discord.Forbidden:
            yield event.plain_result("❌ 权限被拒绝：请确保机器人拥有“管理消息”权限。")
        except Exception as e:
            logger.error(f"Clean Error: {e}")
            yield event.plain_result(f"❌ 执行出错: {str(e)}")
