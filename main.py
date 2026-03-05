
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

    async def clean_messages(self, event: AstrMessageEvent, count: int, user_mention: str = None):

        """

        清理 Discord 消息。

        用法:

        /clean [数量] - 清理当前频道最近的消息

        /clean [数量] [@用户] - 清理当前频道中指定用户的消息

        """



        # 1. 检查当前平台是否为 Discord

        if event.get_platform_name() != "discord":

            yield event.plain_result("❌ 此功能仅在 Discord 平台可用。")

            return



        # 2. 从 AstrBot 事件中获取底层的 discord.py 消息对象

        # 在 AstrBot 的 Discord 适配器中，event.raw_event 通常是 discord.Message 对象

        raw_msg = event.raw_event

        if not hasattr(raw_msg, 'channel'):

            yield event.plain_result("❌ 无法获取 Discord 频道上下文。")

            return



        channel = raw_msg.channel



        try:

            # 3. 逻辑处理：清理特定用户或全员消息

            if user_mention:

                # 处理提到的用户，提取数字 ID (支持 <@123> 或 <@!123> 格式)

                target_user_id = user_mention.strip('<@!>')



                # 定义过滤函数：只删除匹配用户 ID 的消息

                def is_target_user(m):

                    return str(m.author.id) == target_user_id



                # 调用 discord.py 的 purge 方法

                # check 参数用于过滤，limit 是查找消息的最大范围

                deleted = await channel.purge(limit=count, check=is_target_user)

                yield event.plain_result(f"🧹 已清理用户 {user_mention} 的 {len(deleted)} 条消息。")



            else:

                # 4. 普通清理逻辑

                # limit 设置为 count + 1 是为了同时删除用户发送的这条 "/clean" 指令本身

                deleted = await channel.purge(limit=count + 1)



                # 减去指令本身的数量

                actual_deleted = max(0, len(deleted) - 1)

                yield event.plain_result(f"🧹 已成功清理最近的 {actual_deleted} 条消息。")



        except Exception as e:

            # 5. 错误处理：通常是权限不足 (如缺少 Manage Messages 权限)

            logger.error(f"Discord 清理消息失败: {e}")

            yield event.plain_result(f"❌ 清理失败：请检查机器人是否有“管理消息”权限。\n错误信息: {str(e)}")