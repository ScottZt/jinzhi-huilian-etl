"""
工作流调度接口 — 合规设计：封装工具自身调度逻辑，不涉及任何第三方数据源。
"""
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta

from etl_tool_sdk.license import LicenseManager


class WorkflowScheduler:
    """
    工作流调度器 — 提供定时任务调度、断点续传、失败重试能力。

    合规说明：仅封装工具自身调度接口，不涉及任何第三方数据源。

    使用示例：
        scheduler = WorkflowScheduler()

        # 添加定时任务（每日 9:30 执行）
        job_id = scheduler.add_cron_job(
            task_id="daily_sync",
            hour=9, minute=30,
            callback=my_sync_function,
        )

        # 添加间隔任务（每小时执行）
        job_id = scheduler.add_interval_job(
            task_id="hourly_sync",
            interval_seconds=3600,
            callback=my_sync_function,
        )

        # 查看状态
        status = scheduler.get_job_status("daily_sync")
        print(status)

        # 暂停/恢复
        scheduler.pause_job("daily_sync")
        scheduler.resume_job("daily_sync")

        # 移除任务
        scheduler.remove_job("daily_sync")
    """

    def __init__(self):
        self._lm = LicenseManager()
        self._sched = None
        self._job_callbacks: Dict[str, Callable] = {}

    def _get_scheduler(self):
        """懒加载调度器核心。"""
        if self._sched is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                from apscheduler.jobstores.memory import MemoryJobStore
                from apscheduler.executors.pool import ThreadPoolExecutor

                self._sched = BackgroundScheduler(
                    jobstores={"default": MemoryJobStore()},
                    executors={"default": ThreadPoolExecutor(max_workers=5)},
                    job_defaults={"coalesce": True, "max_instances": 1},
                )
                if not self._sched.running:
                    self._sched.start()
            except ImportError:
                raise RuntimeError("APScheduler 库未安装，请运行: pip install apscheduler")
        return self._sched

    def _wrapper(self, task_id: str, func: Callable, *args, **kwargs):
        """任务包装器，自动处理异常和状态记录。"""
        try:
            func(*args, **kwargs)
            self._log_run(task_id, "completed")
        except Exception as e:
            self._log_run(task_id, "failed", str(e))

    def _log_run(self, task_id: str, status: str, error: str = None):
        """记录任务执行状态。"""
        try:
            from etl_tool_sdk.logger import LogHandler
            LogHandler.info(f"定时任务 [{task_id}] {status}", extra={
                "task_id": task_id, "status": status, "error": error,
            })
        except Exception:
            pass

    def add_cron_job(
        self,
        task_id: str,
        callback: Callable,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        second: Optional[int] = None,
        day_of_week: Optional[str] = None,
        day: Optional[int] = None,
        month: Optional[int] = None,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """
        添加 Cron 风格定时任务。

        Args:
            task_id: 任务 ID（唯一标识）
            callback: 回调函数
            hour/minute/second: 定时参数
            day_of_week: 星期几（0-6 或 mon-sun）
            day: 日期
            month: 月份
        Returns:
            job_id
        """
        self._lm.check_feature_or_raise("schedule_cron")

        sched = self._get_scheduler()
        kwargs = kwargs or {}

        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger(
            hour=hour, minute=minute, second=second,
            day_of_week=day_of_week, day=day, month=month,
        )

        self._job_callbacks[task_id] = callback
        job = sched.add_job(
            self._wrapper,
            trigger=trigger,
            args=(task_id, callback) + args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True,
        )
        return job.id

    def add_interval_job(
        self,
        task_id: str,
        callback: Callable,
        interval_seconds: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        interval_hours: Optional[int] = None,
        start_date: Optional[datetime] = None,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """
        添加间隔重复任务。

        Args:
            task_id: 任务 ID
            callback: 回调函数
            interval_seconds/minutes/hours: 间隔时间（至少指定一个）
            start_date: 开始时间
        Returns:
            job_id
        """
        self._lm.check_feature_or_raise("schedule_cron")

        sched = self._get_scheduler()
        kwargs = kwargs or {}

        from apscheduler.triggers.interval import IntervalTrigger

        interval_kwargs = {}
        if interval_seconds:
            interval_kwargs["seconds"] = interval_seconds
        if interval_minutes:
            interval_kwargs["minutes"] = interval_minutes
        if interval_hours:
            interval_kwargs["hours"] = interval_hours

        trigger = IntervalTrigger(start_date=start_date or datetime.now(), **interval_kwargs)

        self._job_callbacks[task_id] = callback
        job = sched.add_job(
            self._wrapper,
            trigger=trigger,
            args=(task_id, callback) + args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True,
        )
        return job.id

    def add_once_job(
        self,
        task_id: str,
        callback: Callable,
        run_date: datetime,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """添加一次性定时任务（在指定时间执行一次）。"""
        sched = self._get_scheduler()
        kwargs = kwargs or {}

        from apscheduler.triggers.date import DateTrigger
        trigger = DateTrigger(run_date=run_date)

        self._job_callbacks[task_id] = callback
        job = sched.add_job(
            self._wrapper,
            trigger=trigger,
            args=(task_id, callback) + args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True,
        )
        return job.id

    def remove_job(self, task_id: str):
        """移除任务。"""
        sched = self._get_scheduler()
        try:
            sched.remove_job(task_id)
        except Exception:
            pass
        self._job_callbacks.pop(task_id, None)

    def pause_job(self, task_id: str):
        """暂停任务。"""
        sched = self._get_scheduler()
        try:
            sched.pause_job(task_id)
        except Exception:
            pass

    def resume_job(self, task_id: str):
        """恢复任务。"""
        sched = self._get_scheduler()
        try:
            sched.resume_job(task_id)
        except Exception:
            pass

    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态。

        Returns:
            {"exists": bool, "next_run": datetime, "pending": bool}
        """
        sched = self._get_scheduler()
        try:
            job = sched.get_job(task_id)
            if job is None:
                return {"exists": False}
            return {
                "exists": True,
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending,
            }
        except Exception:
            return {"exists": False}

    def list_jobs(self) -> list:
        """列出所有任务。"""
        sched = self._get_scheduler()
        try:
            jobs = sched.get_jobs()
            return [
                {
                    "id": j.id,
                    "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                    "pending": j.pending,
                }
                for j in jobs
            ]
        except Exception:
            return []

    def shutdown(self):
        """关闭调度器。"""
        if self._sched and self._sched.running:
            self._sched.shutdown(wait=False)
            self._sched = None
