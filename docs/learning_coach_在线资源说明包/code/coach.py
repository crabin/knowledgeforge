"""
私人学习教练 - 主教练类
"""
from typing import Dict, List, Any, Optional
from datetime import datetime

from coach_data import LearningCoachData
from level_tester import LevelTester
from plan_generator import PlanGenerator
from evaluator import Evaluator
from content_pusher import ContentPusher
from report_generator import ReportGenerator


class LearningCoach:
    """私人学习教练 - 整合所有功能的主类"""

    def __init__(self, user_id: str = "default", base_dir: str = None):
        self.user_id = user_id
        self.data_manager = LearningCoachData(user_id, base_dir)
        self.level_tester = None
        self.plan_generator = None
        self.evaluator = Evaluator()
        self.content_pusher = ContentPusher(self.data_manager)
        self.report_generator = ReportGenerator(self.data_manager)

    def start_new_learning(self,
                          domain: str,
                          daily_time_minutes: int = None,
                          learning_style: str = "theory_practice") -> Dict[str, Any]:
        """
        开始一个新的学习领域

        流程：
        1. 初始化水平测试器
        2. 生成测试题目
        3. 返回测试题目给用户
        """
        # 检查是否已经有学习计划
        existing_plan = self.data_manager.load_plan(domain)
        if existing_plan:
            return {
                "success": False,
                "message": f"你已经在学习 {domain} 领域，可以使用其他命令继续学习。",
                "existing": True
            }

        self.level_tester = LevelTester(domain)

        # 获取测试题目
        test_questions = self.level_tester.get_test_questions()

        return {
            "success": True,
            "message": f"欢迎开始学习 {domain}！首先需要进行水平测试。",
            "domain": domain,
            "test_questions": test_questions,
            "next_step": "请回答以下测试问题，我将根据你的回答制定学习计划。",
            "total_questions": len(test_questions)
        }

    def submit_test_answers(self,
                           domain: str,
                           answers: List[Dict[str, Any]],
                           daily_time_minutes: int = None,
                           learning_style: str = "theory_practice") -> Dict[str, Any]:
        """
        提交水平测试答案

        流程：
        1. 评估答案（需要 LLM）
        2. 生成综合评估
        3. 根据水平生成学习计划
        4. 保存计划
        """
        if not self.level_tester:
            self.level_tester = LevelTester(domain)

        # 评估答案（这里需要调用 LLM，暂时简化）
        # TODO: 集成 LLM 评估
        assessment = self.level_tester.generate_assessment(answers)

        # 保存评估 + 原始回答，确保可追溯
        evaluations = self.data_manager.load_evaluations(domain)
        evaluations["initial_assessment"] = assessment
        self.data_manager.save_evaluations(domain, evaluations)
        self.data_manager.append_evaluation_history(domain, {
            "type": "initial_assessment",
            "domain": domain,
            "submitted_at": datetime.now().isoformat(),
            "raw_answers": answers,
            "assessment": assessment
        })

        # 询问每日学习时间（如果没有提供）
        if daily_time_minutes is None:
            return {
                "success": True,
                "message": f"水平测试完成！你的初始水平：{assessment['level']} (得分: {assessment['score']})",
                "assessment": assessment,
                "next_step": "请告诉我你每天希望花多少分钟学习？（例如：30, 60, 90）",
                "need_daily_time": True
            }

        # 生成学习计划
        self.plan_generator = PlanGenerator(
            domain=domain,
            level=assessment['level'],
            daily_time=daily_time_minutes,
            learning_style=learning_style
        )

        plan = self.plan_generator.generate_plan()
        plan["user_id"] = self.user_id
        self.data_manager.save_plan(domain, plan)

        return {
            "success": True,
            "message": f"水平测试完成！你的初始水平：{assessment['level']} (得分: {assessment['score']})",
            "assessment": assessment,
            "plan": plan,
            "next_step": "学习计划已生成！明天开始，每天我将推送学习内容。",
            "estimated_days": plan.get("estimated_days")
        }

    def get_daily_content(self, domain: str) -> Dict[str, Any]:
        """获取今日学习内容"""
        plan = self.data_manager.load_plan(domain)

        if not plan:
            return {
                "success": False,
                "message": f"还没有 {domain} 的学习计划。请先开始学习。"
            }

        # 检查是否已经完成所有内容
        next_topic = self.content_pusher.get_next_topic(domain, plan)
        if not next_topic:
            # 检查是否需要进行综测
            if self.content_pusher.check_ready_for_final_test(domain):
                return {
                    "success": True,
                    "message": "恭喜！你已经完成了所有学习内容！",
                    "completed_all": True,
                    "ready_for_final_test": True,
                    "suggestion": self.content_pusher.suggest_final_test(domain)
                }
            else:
                return {
                    "success": True,
                    "message": "恭喜！你已经完成了所有学习内容！",
                    "completed_all": True
                }

        # 格式化每日内容
        daily_content = self.content_pusher.format_daily_content(
            domain,
            next_topic,
            plan.get("learning_style", "theory_practice")
        )

        return {
            "success": True,
            "content": daily_content,
            "topic": next_topic,
            "domain": domain
        }

    def submit_daily_answers(self,
                             domain: str,
                             answers: List[str],
                             practice_result: str = "",
                             study_time_minutes: int = None) -> Dict[str, Any]:
        """
        提交每日学习答案

        流程：
        1. 评估答案（需要 LLM）
        2. 评估实践任务
        3. 计算综合得分
        4. 保存学习记录
        5. 更新计划进度
        6. 生成反馈
        """
        plan = self.data_manager.load_plan(domain)

        if not plan:
            return {
                "success": False,
                "message": f"没有找到 {domain} 的学习计划。"
            }

        # 获取当前话题
        current_module_idx = plan.get("current_module_index", 0)
        current_topic_idx = plan.get("current_topic_index", 0)
        modules = plan.get("modules", [])

        if current_module_idx >= len(modules):
            return {
                "success": False,
                "message": "所有学习内容已完成。"
            }

        current_module = modules[current_module_idx]
        topics = current_module.get("topics", [])

        if current_topic_idx >= len(topics):
            return {
                "success": False,
                "message": "当前模块已完成。"
            }

        topic = topics[current_topic_idx]

        # 评估答案（需要 LLM，暂时简化）
        evaluations = []
        for i, answer in enumerate(answers):
            question = {
                "id": f"q{i+1}",
                "content": topic.get("questions", [])[i] if i < len(topic.get("questions", [])) else ""
            }
            eval_result = self.evaluator.evaluate_answer(question, answer)
            # TODO: 调用 LLM 进行实际评估
            eval_result["score"] = 75  # 临时占位
            evaluations.append(eval_result)

        overall_score = self.evaluator.calculate_overall_score(evaluations)

        # 评估实践任务
        practice_eval = None
        if practice_result:
            practice_eval = self.evaluator.evaluate_practice_completion(
                topic.get("practice_task", ""),
                practice_result
            )
            # TODO: 调用 LLM 评估实践任务
            practice_eval["completion_score"] = 80
            practice_eval["quality_score"] = 75

        # 保存学习记录
        record = {
            "date": datetime.now().isoformat(),
            "topic_id": topic["id"],
            "topic_title": topic["title"],
            "study_time_minutes": study_time_minutes or topic.get("estimated_time_minutes", 30),
            "theory_study": True,
            "practice_completed": bool(practice_result),
            "raw_answers": answers,
            "answers": [
                {
                    "question_id": f"q{i+1}",
                    "answer": ans,
                    "evaluation": eval_item
                }
                for i, (ans, eval_item) in enumerate(zip(answers, evaluations))
            ],
            "overall_score": overall_score,
            "practice_evaluation": practice_eval,
            "skipped": False
        }

        self.data_manager.add_learning_record(domain, record)

        # 生成反馈
        feedback_summary = self.evaluator.generate_feedback_summary(evaluations)

        self.data_manager.append_submission_history(domain, {
            "type": "daily_learning",
            "domain": domain,
            "topic_id": topic["id"],
            "topic_title": topic["title"],
            "submitted_at": datetime.now().isoformat(),
            "raw_answers": answers,
            "practice_result": practice_result,
            "practice_evaluation": practice_eval,
            "answer_evaluations": evaluations,
            "overall_score": overall_score,
            "feedback_summary": feedback_summary
        })

        # 更新计划进度
        plan["current_topic_index"] = current_topic_idx + 1
        if plan["current_topic_index"] >= len(topics):
            plan["current_module_index"] = current_module_idx + 1
            plan["current_topic_index"] = 0

        self.data_manager.save_plan(domain, plan)

        # 检查是否需要建议综测
        final_test_suggestion = self.content_pusher.suggest_final_test(domain)

        return {
            "success": True,
            "message": "学习记录已保存！",
            "overall_score": overall_score,
            "feedback": feedback_summary,
            "next_step": "明天继续学习下一个话题。",
            "final_test_suggestion": final_test_suggestion
        }

    def skip_today(self, domain: str) -> Dict[str, Any]:
        """跳过今日学习"""
        return self.content_pusher.skip_day(domain)

    def generate_report(self, domain: str) -> Dict[str, Any]:
        """生成学习报告"""
        report_data = self.report_generator.generate_report(domain)

        return {
            "success": True,
            "report": report_data
        }

    def generate_html_report(self, domain: str) -> str:
        """生成并保存 HTML 学习报告"""
        html_content = self.report_generator.generate_html_report(domain)
        filepath = self.report_generator.save_html_report(domain, html_content)

        return filepath

    def start_final_test(self, domain: str) -> Dict[str, Any]:
        """开始综合测试"""
        plan = self.data_manager.load_plan(domain)

        if not plan:
            return {
                "success": False,
                "message": f"没有找到 {domain} 的学习计划。"
            }

        # 生成综测题目
        final_test_questions = self.evaluator.generate_final_test(plan)

        return {
            "success": True,
            "message": "综合测试已生成，请回答以下问题以评估你的掌握程度。",
            "test_questions": final_test_questions
        }

    def submit_final_test(self,
                         domain: str,
                         answers: Dict[str, str]) -> Dict[str, Any]:
        """提交综测答案"""
        # 评估综测（需要 LLM）
        # TODO: 集成 LLM 评估
        final_score = 85  # 临时占位

        # 保存综测结果
        evaluations = self.data_manager.load_evaluations(domain)
        evaluations["final_assessment"] = {
            "date": datetime.now().isoformat(),
            "score": final_score,
            "answers": answers
        }
        self.data_manager.save_evaluations(domain, evaluations)
        self.data_manager.append_evaluation_history(domain, {
            "type": "final_test",
            "domain": domain,
            "submitted_at": datetime.now().isoformat(),
            "raw_answers": answers,
            "final_score": final_score,
            "mastery_hint": "final_test_completed"
        })

        # 判断掌握程度
        progress = self.data_manager.get_progress(domain)
        mastery = self.evaluator.determine_mastery_level(
            progress.get("completion_rate", 0),
            progress.get("average_score", 0),
            progress.get("practice_completion_rate", 0),
            final_score
        )

        return {
            "success": True,
            "message": "综测完成！",
            "final_score": final_score,
            "mastery": mastery
        }

    def get_progress(self, domain: str) -> Dict[str, Any]:
        """获取学习进度"""
        progress = self.data_manager.get_progress(domain)

        return {
            "success": True,
            "progress": progress
        }

    def list_domains(self) -> List[str]:
        """列出所有正在学习的领域"""
        return self.data_manager.list_domains()

    def delete_domain(self, domain: str) -> Dict[str, Any]:
        """删除一个领域的学习数据"""
        success = self.data_manager.delete_domain(domain)

        return {
            "success": success,
            "message": f"{domain} 的学习数据已删除。" if success else "删除失败。"
        }

    def get_weekly_summary(self, domain: str) -> str:
        """获取周总结"""
        return self.content_pusher.generate_weekly_summary(domain)
