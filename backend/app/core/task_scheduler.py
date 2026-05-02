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

    _load_tasks_from_db()
    return _scheduler


def _load_tasks_from_db():
    if _scheduler is None:
        return
    tasks = sqlite_repo.list_tasks()
    for task in tasks:
        if task.get("cron_expression"):
            schedule_task(task["id"], task["cron_expression"], _job_callbacks.get(task["id"]))


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


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Task scheduler shutdown")
