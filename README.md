# OMS3 Report Service

`OMS3` - микросервис асинхронного построения отчетов. Сервис создает ресурс задачи формирования отчета (`ReportTask`), позволяет проверять ее состояние, отменять задачу и получать ссылку на результат после завершения.

## Функции

- Прием запроса на асинхронное построение отчета.
- Создание ресурса `ReportTask`.
- Возврат `202 Accepted`, `Location` и `Retry-After` при запуске операции.
- Получение состояния задачи отчета.
- Получение ссылки на скачивание результата.
- Отмена задачи отчета.
- Публикация события `report.requested` в Kafka.

## Ресурс задачи отчета

`ReportTask` - ресурс, представляющий одну задачу асинхронного формирования отчета и ее жизненный цикл.

Ресурс содержит:

- `taskId` - идентификатор задачи.
- `status` - текущее состояние.
- `progress` - прогресс выполнения.
- `parameters` - параметры запуска отчета.
- `result` - ссылка на результат после завершения.
- `error` - ошибка при неуспешном завершении.
- `createdAt`, `updatedAt`, `startedAt`, `completedAt`, `expiresAt` - временные метки.

Статусы:

| Статус | Значение |
| --- | --- |
| `queued` | Задача поставлена в очередь |
| `running` | Отчет формируется |
| `completed` | Отчет готов |
| `failed` | Формирование завершилось ошибкой |
| `cancelled` | Задача отменена |
| `expired` | Результат больше недоступен |

## Технологии

- Python 3.11
- FastAPI
- Uvicorn
- confluent-kafka

## API

### Health check

```http
GET /health
```

### Запустить формирование отчета

```http
POST /api/v1/report-tasks
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <uuid>
```

Тело запроса:

```json
{
  "reportType": "orders",
  "filter": {
    "createdFrom": "2026-09-01",
    "createdTo": "2026-09-12",
    "status": ["completed"]
  },
  "format": "xlsx"
}
```

Ответ `202 Accepted`:

```http
HTTP/1.1 202 Accepted
Location: /api/v1/report-tasks/tsk_123
Retry-After: 5
Content-Type: application/json
```

```json
{
  "taskId": "tsk_123",
  "status": "queued",
  "statusUrl": "/api/v1/report-tasks/tsk_123",
  "createdAt": "2026-09-12T03:50:00Z"
}
```

### Получить статус задачи

```http
GET /api/v1/report-tasks/{taskId}
Authorization: Bearer <token>
```

Пример `running`:

```json
{
  "taskId": "tsk_123",
  "status": "running",
  "progress": 65,
  "createdAt": "2026-09-12T03:50:00Z",
  "updatedAt": "2026-09-12T03:53:12Z"
}
```

Пример `completed`:

```json
{
  "taskId": "tsk_123",
  "status": "completed",
  "progress": 100,
  "result": {
    "fileName": "orders-2026-09-12.xlsx",
    "downloadUrl": "/api/v1/report-tasks/tsk_123/download",
    "expiresAt": "2026-09-12T04:50:00Z"
  }
}
```

### Скачать результат

```http
GET /api/v1/report-tasks/{taskId}/download
Authorization: Bearer <token>
```

Ответ:

```json
{
  "downloadUrl": "https://storage.example.local/reports/orders-2026-09-12.xlsx",
  "expiresAt": "2026-09-12T04:50:00Z"
}
```

### Отменить задачу

```http
DELETE /api/v1/report-tasks/{taskId}
Authorization: Bearer <token>
```

Успешный ответ:

```http
HTTP/1.1 204 No Content
```

## Kafka events

- `report.requested` - создан запрос на построение отчета.
- `report.cancelled` - задача отчета отменена.

## Переменные окружения

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `SERVICE_NAME` | `OMS3` | Имя сервиса |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka.oms.svc.cluster.local:9092` | Kafka bootstrap servers |

## Локальный запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8003
```

Встроенный Swagger UI FastAPI для OMS3:

```text
http://localhost:8003/docs
```

Это Swagger только текущего сервиса OMS3. Общая Swagger UI страница для единой спецификации `platform/contracts/openapi_oms_microservices.json` запускается отдельно из корня проекта и открывается без `/docs`:

```powershell
docker run --rm `
  --name oms-swagger-ui `
  -p 8088:8080 `
  -e SWAGGER_JSON=/spec/platform/contracts/openapi_oms_microservices.json `
  -v "D:/ProjectsDocker/extrawork:/spec" `
  swaggerapi/swagger-ui:v5.17.14
```

```text
http://localhost:8088
```

Через Ingress сервис доступен без port-forward. Встроенный Swagger UI OMS3:

```text
http://oms.local/oms3/docs
```

## Docker

```bash
docker build -t oms3:latest .
docker run --rm -p 8003:8000 oms3:latest
```

## Kubernetes

```bash
kubectl apply -f ../platform/k8s/namespace.yaml
kubectl apply -f k8s/
kubectl -n oms port-forward svc/oms3 8003:80
```

После port-forward встроенный Swagger UI OMS3 доступен по адресу:

```text
http://localhost:8003/docs
```

## Дальнейшее развитие

- Добавить постоянное хранилище статусов отчетов.
- Добавить lightweight worker для построения отчетов через RabbitMQ. Kafka хранит события как durable event log в пределах настроенной retention policy.
- Добавить форматы выгрузки: XLSX, CSV, PDF.
- Добавить авторизацию через `OMS1`.
