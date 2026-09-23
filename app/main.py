from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.healthcheck.router import router as healthcheck_router
from app.kafka import publish_event
from app.settings import settings

app = FastAPI(title="OMS3 Report Service", version="0.1.0", root_path=settings.root_path)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8088", "http://127.0.0.1:8088"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(healthcheck_router)

report_tasks: dict[str, dict] = {}


class ReportTaskCreate(BaseModel):
    report_type: str = Field(alias="reportType", examples=["orders"])
    filter: dict = Field(default_factory=dict)
    format: str = Field(default="xlsx", examples=["xlsx"])

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        allowed = {"xlsx", "csv", "pdf"}
        if value not in allowed:
            raise ValueError(f"format must be one of: {', '.join(sorted(allowed))}")
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_task(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "parameters"} | {"parameters": task["parameters"]}


def refresh_task_status(task: dict) -> dict:
    if task["status"] in {"completed", "failed", "cancelled", "expired"}:
        return task

    elapsed = (utcnow() - task["createdAt"]).total_seconds()
    if elapsed < 5:
        task["status"] = "queued"
        task["progress"] = 0
    elif elapsed < 15:
        task["status"] = "running"
        task["progress"] = 65
        task["startedAt"] = task["startedAt"] or utcnow()
    else:
        report_id = task["reportId"] or f"rpt_{uuid4().hex[:12]}"
        task.update(
            {
                "status": "completed",
                "progress": 100,
                "reportId": report_id,
                "completedAt": utcnow(),
                "result": {
                    "fileName": f"{task['parameters']['reportType']}-{task['id']}.{task['parameters']['format']}",
                    "downloadUrl": f"/api/v1/report-tasks/{task['id']}/download",
                    "expiresAt": utcnow() + timedelta(hours=1),
                },
            }
        )
    task["updatedAt"] = utcnow()
    return task


@app.post("/api/v1/report-tasks", status_code=status.HTTP_202_ACCEPTED)
def start_report_generation(payload: ReportTaskCreate, response: Response) -> dict:
    task_id = f"tsk_{uuid4().hex[:12]}"
    now = utcnow()
    task = {
        "id": task_id,
        "taskId": task_id,
        "status": "queued",
        "progress": 0,
        "statusUrl": f"/api/v1/report-tasks/{task_id}",
        "createdAt": now,
        "updatedAt": now,
        "startedAt": None,
        "completedAt": None,
        "expiresAt": now + timedelta(hours=24),
        "reportId": None,
        "parameters": payload.model_dump(by_alias=True),
        "result": None,
        "error": None,
    }
    report_tasks[task_id] = task
    response.headers["Location"] = task["statusUrl"]
    response.headers["Retry-After"] = "5"
    event = {"task_id": task_id, "status": "queued", "request": task["parameters"], "created_at": now}
    publish_event("report.requested", event)
    return {"taskId": task_id, "status": "queued", "statusUrl": task["statusUrl"], "createdAt": now}


@app.get("/api/v1/report-tasks/{task_id}")
def get_report_task_status(task_id: str, response: Response) -> dict:
    task = report_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report task not found")
    refresh_task_status(task)
    if task["status"] in {"queued", "running"}:
        response.headers["Retry-After"] = "5"
    return serialize_task(task)


@app.get("/api/v1/report-tasks/{task_id}/download")
def download_report(task_id: str) -> dict:
    task = report_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report task not found")
    refresh_task_status(task)
    if task["status"] != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not ready")
    return {"downloadUrl": f"https://storage.example.local/reports/{task['result']['fileName']}", "expiresAt": task["result"]["expiresAt"]}


@app.delete("/api/v1/report-tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_report_task(task_id: str) -> Response:
    task = report_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report task not found")
    refresh_task_status(task)
    if task["status"] == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed report task cannot be cancelled")
    task["status"] = "cancelled"
    task["updatedAt"] = utcnow()
    publish_event("report.cancelled", {"task_id": task_id, "cancelled_at": task["updatedAt"]})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/reports", status_code=status.HTTP_202_ACCEPTED)
def request_report_legacy(payload: ReportTaskCreate, response: Response) -> dict:
    return start_report_generation(payload, response)


@app.get("/reports/{task_id}")
def get_report_legacy(task_id: str, response: Response) -> dict:
    return get_report_task_status(task_id, response)
