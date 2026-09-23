# Sequence-диаграммы — `src/api/routes/`

## `GET /health`

Liveness-проверка процесса. Ошибочных веток нет: обработчик не выполняет
ввод-вывода (не обращается к БД и не ходит в OSRM) и ничем, кроме самого
факта ответа процесса, не может завершиться иначе как `200`.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (health route)

    Client->>API: GET /health
    API-->>Client: 200 {status: "ok", version}
```
