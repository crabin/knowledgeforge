"""
私人学习教练 - 内容推送器模块
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import random

from online_resource import OnlineResourceFetcher


class ContentPusher:
    """内容推送器 - 管理学习内容的每日推送"""

    def __init__(self, data_manager, enable_online_resources: bool = True):
        self.data_manager = data_manager
        self.enable_online_resources = enable_online_resources
        self.online_fetcher = OnlineResourceFetcher() if enable_online_resources else None

    def get_next_topic(self, domain: str, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取下一个要学习的话题"""
        # 从计划中获取当前进度
        current_module_idx = plan.get("current_module_index", 0)
        current_topic_idx = plan.get("current_topic_index", 0)

        modules = plan.get("modules", [])

        if current_module_idx >= len(modules):
            # 所有模块都完成了
            return None

        current_module = modules[current_module_idx]
        topics = current_module.get("topics", [])

        if current_topic_idx >= len(topics):
            # 当前模块完成，进入下一个模块
            current_module_idx += 1
            current_topic_idx = 0

            if current_module_idx >= len(modules):
                return None

            current_module = modules[current_module_idx]
            topics = current_module.get("topics", [])

        if current_topic_idx >= len(topics):
            return None

        topic = topics[current_topic_idx]
        return {
            "topic": topic,
            "module_index": current_module_idx,
            "topic_index": current_topic_idx
        }

    def format_daily_content(self,
                            domain: str,
                            topic: Dict[str, Any],
                            learning_style: str) -> str:
        """格式化每日学习内容，含在线资源"""
        topic_data = topic["topic"]
        module_index = topic["module_index"]
        topic_index = topic["topic_index"]

        # 尝试获取在线资源
        online_section = ""
        if self.online_fetcher:
            try:
                online_resources = self.online_fetcher.search_resources(
                    domain, topic_data["title"], max_results=3
                )
                if online_resources:
                    online_section = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n🌐 最新在线资源：\n"
                    for r in online_resources:
                        type_emoji = {"video": "🎬", "paper": "📄", "tutorial": "📝",
                                     "code": "💻", "documentation": "📖"}.get(r["type"], "🔗")
                        online_section += f'{type_emoji} {r["title"]}\n   {r["url"]}\n'
            except Exception:
                pass  # 在线资源获取失败不影响主流程

        # 生成每日推送内容
        content = f"""
📚 今日学习内容 - {domain.upper()}

📍 进度：模块 {module_index + 1} / 话题 {topic_index + 1}

━━━━━━━━━━━━━━━━━━━━━━━━

【话题】{topic_data['title']}

━━━━━━━━━━━━━━━━━━━━━━━━

📖 理论学习：
{topic_data['theory_content']}

━━━━━━━━━━━━━━━━━━━━━━━━

🎯 实践任务：
{topic_data['practice_task']}

━━━━━━━━━━━━━━━━━━━━━━━━

❓ 思考题：
"""
        for i, question in enumerate(topic_data['questions'], 1):
            content += f"{i}. {question}\n"

        content += f"""
━━━━━━━━━━━━━━━━━━━━━━━━

💡 关键概念：
{', '.join(topic_data['key_concepts'])}

━━━━━━━━━━━━━━━━━━━━━━━━

📚 推荐资源：
"""
        for resource in topic_data['resources']:
            content += f"- {resource}\n"

        content += online_section

        content += f"""
━━━━━━━━━━━━━━━━━━━━━━━━

⏰ 预计学习时间：{topic_data.get('estimated_time_minutes', 30)} 分钟

请完成理论学习后，回答思考题并完成实践任务，然后告诉我你的答案。
"""

        return content

    def generate_push_schedule(self,
                               domain: str,
                               plan: Dict[str, Any],
                               daily_time: str = "09:00") -> Dict[str, Any]:
        """生成推送计划"""
        start_date = datetime.fromisoformat(plan["start_date"])
        estimated_days = plan.get("estimated_days", 30)

        schedule = {
            "domain": domain,
            "start_date": start_date.isoformat(),
            "daily_push_time": daily_time,
            "estimated_days": estimated_days,
            "total_pushes": estimated_days,
            "created_at": datetime.now().isoformat()
        }

        return schedule

    def skip_day(self, domain: str) -> Dict[str, Any]:
        """跳过一天学习"""
        records = self.data_manager.load_records(domain)

        skip_record = {
            "date": datetime.now().isoformat(),
            "skipped": True,
            "reason": "用户跳过",
            "next_topic": None
        }

        self.data_manager.add_learning_record(domain, skip_record)

        return {
            "success": True,
            "message": "已跳过今日学习，明天继续。",
            "skipped_date": skip_record["date"]
        }

    def get_review_questions(self, domain: str, count: int = 3) -> List[str]:
        """生成复习问题"""
        # 从已完成的话题中随机选择一些概念出复习题
        records = self.data_manager.load_records(domain)
        completed_topics = [r["topic_id"] for r in records.get("records", []) if not r.get("skipped")]

        if not completed_topics:
            return []

        # 随机选择几个已完成的话题
        review_topics = random.sample(completed_topics, min(count, len(completed_topics)))

        review_questions = []
        for topic_id in review_topics:
            # 从计划中找到这个话题
            plan = self.data_manager.load_plan(domain)
            if plan:
                for module in plan.get("modules", []):
                    for topic in module.get("topics", []):
                        if topic["id"] == topic_id:
                            # 生成复习题
                            review_questions.append(
                                f"复习：{topic['title']} - 请回顾{topic['key_concepts'][0]}等核心概念"
                            )
                            break

        return review_questions

    def generate_weekly_summary(self, domain: str) -> str:
        """生成周总结"""
        records = self.data_manager.load_records(domain)
        plan = self.data_manager.load_plan(domain)

        if not records or not plan:
            return "暂无学习数据"

        recent_records = [
            r for r in records.get("records", [])
            if not r.get("skipped") and r.get("date")
        ]

        if not recent_records:
            return "本周还没有完成学习"

        # 计算本周的学习情况
        total_study_time = sum(r.get("study_time_minutes", 0) for r in recent_records[-7:])
        completed_topics = len(recent_records[-7:])
        avg_score = 0

        scored_records = [r for r in recent_records[-7:] if "overall_score" in r]
        if scored_records:
            avg_score = sum(r["overall_score"] for r in scored_records) / len(scored_records)

        summary = f"""
📊 本周学习总结 - {domain.upper()}

━━━━━━━━━━━━━━━━━━━━━━━━

📈 学习统计：
• 完成话题：{completed_topics} 个
• 学习时长：{total_study_time} 分钟
• 平均分数：{avg_score:.1f} 分

━━━━━━━━━━━━━━━━━━━━━━━━

"""

        progress = self.data_manager.get_progress(domain)
        if "completion_rate" in progress:
            summary += f"📊 总体进度：{progress['completion_rate']}% 完成\n\n"

        summary += f"继续加油！你已经完成了本周的学习目标。"

        return summary

    def check_ready_for_final_test(self, domain: str) -> bool:
        """检查是否准备好进行综测"""
        progress = self.data_manager.get_progress(domain)

        # 标准：完成率>90% 且 平均分>80
        completion_rate = progress.get("completion_rate", 0)
        average_score = progress.get("average_score", 0)

        if completion_rate >= 90 and average_score >= 80:
            return True

        return False

    def suggest_final_test(self, domain: str) -> Optional[str]:
        """建议进行综测"""
        if self.check_ready_for_final_test(domain):
            return """
🎉 恭喜！你的学习进度非常优秀！

根据你的学习数据：
• 已完成超过 90% 的学习内容
• 平均得分超过 80 分

建议你现在进行综合测试，以确认你对本领域的掌握程度。

准备好后，告诉我"开始综测"，我将为你生成综合测试题目。
"""

        return None
