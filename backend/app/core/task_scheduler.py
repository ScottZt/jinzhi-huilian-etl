import logging
from typing import Dict, Optional, Callable
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.persistence import sqlite_repo

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_job_callbacks: Dict[str, Callable] = {}
# 按"任务类型"注册默认执行器，用于服务重启后从 DB 恢复定时任务
# 目前支持： "task" (tasks 表) / "pipeline" (pipelines 表)
_executors: Dict[str, Callable] = {}


def register_executor(kind: str, fn: Callable):
    """注册某类任务的默认执行器（接收 task_id/pipeline_id 单参数）。"""
    _executors[kind] = fn
    logger.info(f"Executor registered for kind={kind!r}")


def _on_job_executed(event):
    job_id = event.job_id
    if event.exception:
        logger.error(f"Job {job_id} failed: {event.exception}")
        _update_task_status(job_id, "failed", str(event.exception))
    else:
        logger.info(f"Job {job_id} completed successfully")
        _update_task_status(job_id, "completed")


def _update_task_status(task_id: str, status: str, error: str = None):
    task = sqlite_repo.get_task(task_id)
    if task:
        task["status"] = status
        task["last_run_at"] = datetime.utcnow().isoformat()
        task["updated_at"] = datetime.utcnow().isoformat()
        if error:
            task["config_json"]["last_error"] = error
        try:
            sqlite_repo.save_task(task)
        except Exception:
            pass


def init_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(
        jobstores={"default": MemoryJobStore()},
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        },
        timezone="Asia/Shanghai",
    )

    _scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    _scheduler.start()
    logger.info("Task scheduler started (Asia/Shanghai timezone)")
    print(f"[SCHEDULER] 定时任务调度器已启动 (Asia/Shanghai)")

    _load_tasks_from_db()
    return _scheduler


def _load_tasks_from_db():
    if _scheduler is None:
        return

    # 1) 恢复 tasks 表的定时任务
    tasks = sqlite_repo.list_tasks()
    task_exec = _executors.get("task")
    restored_tasks = 0
    for task in tasks:
        if task.get("cron_expression"):
            cb = _job_callbacks.get(task["id"]) or task_exec
            if cb and schedule_task(task["id"], task["cron_expression"], cb):
                restored_tasks += 1
    if restored_tasks:
        print(f"[SCHEDULER] 已恢复 {restored_tasks} 个任务的定时执行")

    # 2) 恢复 pipelines 表的定时任务（仅 enabled=1 且 cron_expression 非空）
    pipeline_exec = _executors.get("pipeline")
    if not pipeline_exec:
        print(f"[SCHEDULER] 警告: pipeline executor 未注册，跳过数据流定时恢复")
        return
    try:
        pipelines = sqlite_repo.list_pipelines()
    except Exception as e:
        print(f"[SCHEDULER] 错误: 读取数据流列表失败: {e}")
        return
    restored_pipelines = 0
    for p in pipelines:
        if not p.get("enabled"):
            continue
        cron = p.get("cron_expression")
        if not cron:
            continue
        # 若已有 runtime 注册的回调（理论上 pipeline 不会走 _job_callbacks，保留兜底）
        cb = _job_callbacks.get(p["id"]) or pipeline_exec
        if schedule_task(p["id"], cron, cb):
            restored_pipelines += 1
            print(
                f"[SCHEDULER] 已恢复数据流定时任务: {p.get('name')!r} "
                f"(cron={cron.strip()})"
            )
    print(f"[SCHEDULER] 数据流定时恢复完成: {restored_pipelines}/{len(pipelines)}")


def get_scheduler() -> BackgroundScheduler:
    if _scheduler is None:
        return init_scheduler()
    return _scheduler


def schedule_task(task_id: str, cron_expr: str, callback: Optional[Callable] = None):
    if _scheduler is None:
        init_scheduler()

    remove_task(task_id)

    if callback:
        _job_callbacks[task_id] = callback

    try:
        parts = cron_expr.strip().split()
        if len(parts) == 5:
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
                timezone="Asia/Shanghai",
            )
        elif len(parts) == 6:
            trigger = CronTrigger(
                second=parts[0], minute=parts[1], hour=parts[2],
                day=parts[3], month=parts[4], day_of_week=parts[5],
                timezone="Asia/Shanghai",
            )
        else:
            logger.warning(f"Invalid cron expression for task {task_id}: {cron_expr}")
            return False

        _scheduler.add_job(
            _run_task_wrapper,
            trigger=trigger,
            id=task_id,
            args=[task_id],
            name=f"task_{task_id}",
            replace_existing=True,
        )

        next_run = _scheduler.get_job(task_id)
        if next_run:
            next_run_time = next_run.next_run_time
            task = sqlite_repo.get_task(task_id)
            if task:
                task["next_run_at"] = next_run_time.isoformat() if next_run_time else None
                sqlite_repo.save_task(task)

        logger.info(f"Scheduled task {task_id} with cron: {cron_expr}")
        return True
    except Exception as e:
        logger.error(f"Failed to schedule task {task_id}: {e}")
        return False


def remove_task(task_id: str):
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(task_id)
        _job_callbacks.pop(task_id, None)
        logger.info(f"Removed scheduled task {task_id}")
    except Exception:
        pass


def run_task_now(task_id: str) -> str:
    task = sqlite_repo.get_task(task_id)
    if not task:
        return f"Task {task_id} not found"

    task["status"] = "running"
    task["last_run_at"] = datetime.utcnow().isoformat()
    task["updated_at"] = datetime.utcnow().isoformat()
    sqlite_repo.save_task(task)

    if _scheduler:
        job = _scheduler.get_job(task_id)
        if job:
            job.modify(next_run_time=None)

    try:
        _run_task_wrapper(task_id)
        return "Task executed successfully"
    except Exception as e:
        return f"Task execution failed: {e}"


def _run_task_wrapper(task_id: str):
    callback = _job_callbacks.get(task_id)
    if callback:
        try:
            callback(task_id)
        except Exception as e:
            logger.error(f"Task {task_id} callback failed: {e}")
            raise
    else:
        logger.info(f"Task {task_id} executed (no callback registered)")


def get_next_run_times(limit: int = 10) -> list:
    if _scheduler is None:
        return []
    jobs = _scheduler.get_jobs()
    result = []
    for job in jobs:
        next_time = job.next_run_time
        if next_time:
            result.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_time.isoformat(),
            })
    return sorted(result, key=lambda x: x["next_run"])[:limit]


def get_next_run_for_id(task_id: str) -> Optional[str]:
    """获取指定任务的下次执行时间（ISO 格式字符串），未找到返回 None。"""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(task_id)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Task scheduler shutdown")
