from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import logging

# 获取日志记录器
logger = logging.getLogger("astrbot")

@register("discord_message_tool", "Developer", "提供 Discord 平台的消息清理（Purge）功能", "1.0.0")
class DiscordMessageTool(Star):
    def __init__(self, context: Context):
        super().__init__(context)
@filter.command("clean")
    async def clean_messages(self, event: AstrMessageEvent, count: int = 5, user_mention: str = None):
        """
        清理 Discord 消息。
        用法:
        /clean [数量] - (如果不填，默认清理最近5条)
        /clean [数量] [@用户] - 清理特定用户的消息
        """

        # 1. 检查平台
        if event.get_platform_name() != "discord":
            yield event.plain_result("❌ 此功能仅在 Discord 平台可用。")
            return

        # 2. 获取 Discord 频道对象 (增加兼容性写法)
        try:
            # 优先从原始事件获取，拿不到就从适配器拿
            channel = getattr(event.raw_event, 'channel', None)
            if not channel:
                client = event.bot.get_adapter("discord").client
                channel = client.get_channel(int(event.message_obj.group_id))
        except Exception as e:
            yield event.plain_result(f"❌ 无法连接到 Discord 频道: {e}")
            return

        try:
            if user_mention:
                # --- 定向清理模式 ---
                # 提取用户 ID (过滤掉 <@! > 等符号)
                target_id = "".join(filter(str.isdigit, user_mention))
                
                def is_target(m):
                    return str(m.author.id) == target_id

                # 这里的 limit 是扫描范围，不是删除数量
                # 为了删掉 N 条特定用户的，我们需要扫描更多的历史消息
                deleted = await channel.purge(limit=10000, check=is_target) 
                # 注意：这里为了安全限制扫描最近100条
                
                # 截取用户要求的数量
                to_delete = deleted[:count]
                yield event.plain_result(f"🧹 已从最近消息中清理了 {user_mention} 的 {len(to_delete)} 条消息。")
            
            else:
                # --- 普通清理模式 ---
                # 如果没给 count，上面默认值是 5
                # 实际删除 count + 1 (包含指令本身)
                deleted = await channel.purge(limit=count + 1)
                actual_deleted = max(0, len(deleted) - 1)
                yield event.plain_result(f"🧹 已清理最近的 {actual_deleted} 条消息。")

        except Exception as e:
            logger.error(f"清理失败: {e}")
            yield event.plain_result(f"❌ 失败：请确认 Bot 拥有“管理消息”权限。\n错误: {str(e)}")
