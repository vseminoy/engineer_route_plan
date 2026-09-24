"""initial schema

Revision ID: 5d23f2956ce7
Revises:
Create Date: 2026-09-23 23:48:02.691132

All timestamps are `TIMESTAMP(0)` without time zone and carry the region's local
time exactly as the application wrote it, to the second — the precision the API
accepts and returns. No column defaults to `now()`: it returns `timestamptz`, and
casting it to `TIMESTAMP` would silently apply the server's time zone.
"""
import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5d23f2956ce7'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("regions", "engineers", "tickets", "plans", "assignments", "replan_events")

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE regions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    office_address  TEXT NOT NULL,
    office_geom     geometry(Point, 4326) NOT NULL,
    CONSTRAINT ux_regions__code UNIQUE (code)
);

CREATE TABLE engineers (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id     BIGINT NOT NULL REFERENCES regions (id),
    name          TEXT NOT NULL,
    start_geom    geometry(Point, 4326) NOT NULL,
    shift_start   TIME NOT NULL,
    shift_end     TIME NOT NULL,
    vehicle_type  TEXT NOT NULL,
    skills        TEXT[] NOT NULL,
    CONSTRAINT ck_engineers__shift_order CHECK (shift_start < shift_end),
    CONSTRAINT ck_engineers__vehicle_type
        CHECK (vehicle_type IN ('car', 'foot', 'bike', 'public_transport')),
    CONSTRAINT ck_engineers__skills
        CHECK (array_ndims(skills) = 1
               AND cardinality(skills) BETWEEN 1 AND 3
               AND skills <@ ARRAY['local_work', 'connection', 'emergency']::TEXT[])
);

CREATE TABLE tickets (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id                 BIGINT NOT NULL REFERENCES regions (id),
    external_id               TEXT NOT NULL,
    type_bk                   TEXT,
    type_hd                   TEXT,
    required_skill            TEXT NOT NULL,
    required_vehicle          TEXT,
    priority                  SMALLINT NOT NULL,
    district                  TEXT,
    address                   TEXT NOT NULL,
    geom                      geometry(Point, 4326) NOT NULL,
    window_start              TIMESTAMP(0) NOT NULL,
    window_end                TIMESTAMP(0) NOT NULL,
    duration_min              INTEGER NOT NULL,
    status                    TEXT NOT NULL,
    received_at               TIMESTAMP(0) NOT NULL,
    cancelled_after_dispatch  BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_tickets__required_skill
        CHECK (required_skill IN ('local_work', 'connection', 'emergency')),
    CONSTRAINT ck_tickets__required_vehicle
        CHECK (required_vehicle IN ('car', 'foot', 'bike', 'public_transport')),
    CONSTRAINT ck_tickets__priority_rank CHECK (priority >= 1),
    CONSTRAINT ck_tickets__window_order CHECK (window_start < window_end),
    CONSTRAINT ck_tickets__duration_positive CHECK (duration_min > 0),
    CONSTRAINT ck_tickets__status
        CHECK (status IN ('not_sent', 'sent', 'en_route', 'in_progress',
                          'completed', 'cancelled', 'overdue'))
);

CREATE TABLE plans (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id       BIGINT NOT NULL REFERENCES regions (id),
    plan_date       DATE NOT NULL,
    algorithm       TEXT NOT NULL,
    parent_plan_id  BIGINT REFERENCES plans (id),
    created_at      TIMESTAMP(0) NOT NULL,
    CONSTRAINT ck_plans__algorithm CHECK (algorithm IN ('or_tools', 'baseline_fcfs'))
);

CREATE TABLE assignments (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id            BIGINT NOT NULL REFERENCES plans (id),
    ticket_id          BIGINT NOT NULL REFERENCES tickets (id),
    engineer_id        BIGINT REFERENCES engineers (id),
    sequence_no        INTEGER,
    planned_arrival    TIMESTAMP(0),
    travel_time_min    INTEGER,
    travel_distance_m  INTEGER,
    unassigned_reason  TEXT,
    explanation        TEXT NOT NULL,
    CONSTRAINT ux_assignments__plan_id_ticket_id UNIQUE (plan_id, ticket_id),
    CONSTRAINT ux_assignments__plan_id_engineer_id_sequence_no
        UNIQUE (plan_id, engineer_id, sequence_no),
    CONSTRAINT ck_assignments__sequence_no_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_assignments__travel_non_negative
        CHECK (travel_time_min >= 0 AND travel_distance_m >= 0),
    CONSTRAINT ck_assignments__planned_arrival_whole_minute
        CHECK (planned_arrival = date_trunc('minute', planned_arrival)),
    CONSTRAINT ck_assignments__unassigned_reason
        CHECK (unassigned_reason IN ('no_skill', 'no_time_slot', 'no_vehicle',
                                     'shift_overflow', 'no_equipment',
                                     'all_eligible_engineers_booked_elsewhere')),
    CONSTRAINT ck_assignments__assigned_or_reason CHECK (
        (engineer_id IS NOT NULL AND sequence_no IS NOT NULL
         AND planned_arrival IS NOT NULL AND travel_time_min IS NOT NULL
         AND travel_distance_m IS NOT NULL AND unassigned_reason IS NULL)
        OR
        (engineer_id IS NULL AND sequence_no IS NULL
         AND planned_arrival IS NULL AND travel_time_min IS NULL
         AND travel_distance_m IS NULL AND unassigned_reason IS NOT NULL)
    )
);

CREATE TABLE replan_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id         BIGINT NOT NULL REFERENCES plans (id),
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    triggered_at    TIMESTAMP(0) NOT NULL,
    result_plan_id  BIGINT REFERENCES plans (id),
    CONSTRAINT ck_replan_events__event_type
        CHECK (event_type IN ('new_urgent_ticket', 'new_ticket',
                              'ticket_cancelled', 'engineer_unavailable'))
);

CREATE INDEX ix_regions__office_geom ON regions USING GIST (office_geom);
CREATE INDEX ix_engineers__region_id ON engineers (region_id);
CREATE INDEX ix_engineers__start_geom ON engineers USING GIST (start_geom);
CREATE INDEX ix_tickets__region_id_window_start ON tickets (region_id, window_start);
CREATE INDEX ix_tickets__region_id_status ON tickets (region_id, status);
CREATE INDEX ix_tickets__geom ON tickets USING GIST (geom);
CREATE INDEX ix_plans__region_id_plan_date ON plans (region_id, plan_date);
CREATE INDEX ix_plans__parent_plan_id ON plans (parent_plan_id);
CREATE INDEX ix_assignments__ticket_id ON assignments (ticket_id);
CREATE INDEX ix_assignments__engineer_id ON assignments (engineer_id);
CREATE INDEX ix_replan_events__plan_id ON replan_events (plan_id);
CREATE INDEX ix_replan_events__result_plan_id ON replan_events (result_plan_id);

COMMENT ON TABLE regions IS 'Регион: независимый сценарий планирования; заявки и бригады разных регионов вместе не планируются';
COMMENT ON COLUMN regions.code IS 'Код региона латиницей (east, south_east, south_center); по нему регион выбирают в API';
COMMENT ON COLUMN regions.name IS 'Название региона для показа пользователю';
COMMENT ON COLUMN regions.office_address IS 'Адрес офиса региона из служебной строки входного файла';
COMMENT ON COLUMN regions.office_geom IS 'Точка офиса региона (WGS84); по умолчанию из неё начинают смену бригады региона';

COMMENT ON TABLE engineers IS 'Бригада: одна запись — одна бригада региона, в модели планирования — одно транспортное средство';
COMMENT ON COLUMN engineers.region_id IS 'Регион бригады; бригада получает заявки только своего региона';
COMMENT ON COLUMN engineers.name IS 'Название бригады для показа; персональных данных не содержит';
COMMENT ON COLUMN engineers.start_geom IS 'Точка, из которой бригада начинает смену (WGS84)';
COMMENT ON COLUMN engineers.shift_start IS 'Начало смены, местное время региона; дата берётся из даты плана';
COMMENT ON COLUMN engineers.shift_end IS 'Конец смены, местное время региона; смена не переходит через полночь, вся занятость бригады укладывается в неё';
COMMENT ON COLUMN engineers.vehicle_type IS 'Транспорт бригады; определяет профиль расчёта пути по дорожной сети';
COMMENT ON COLUMN engineers.skills IS 'Навыки бригады: от 1 до 3 значений из local_work, connection, emergency';

COMMENT ON TABLE tickets IS 'Заявка на выезд: одна запись — одна заявка из входных данных региона';
COMMENT ON COLUMN tickets.region_id IS 'Регион заявки; её могут взять только бригады этого региона';
COMMENT ON COLUMN tickets.external_id IS 'Номер заявки из входного файла (поле «Заявка»)';
COMMENT ON COLUMN tickets.type_bk IS 'Тип заявки BK из входного файла как есть; NULL — поле пусто';
COMMENT ON COLUMN tickets.type_hd IS 'Тип заявки HD из входного файла как есть; NULL — поле пусто';
COMMENT ON COLUMN tickets.required_skill IS 'Навык, без которого бригада не может взять заявку; выведен из типов BK/HD таблицей соответствия, для HD = Авария всегда emergency';
COMMENT ON COLUMN tickets.required_vehicle IS 'Транспорт, которым должна приехать бригада; NULL — подходит любой';
COMMENT ON COLUMN tickets.priority IS 'Ранг приоритета типа работ, 1 — самый срочный: 1 авария, 2 подключение, 3 ремонт и дозаказ; задаётся таблицей соответствия типов заявок, новый уровень не требует изменения схемы';
COMMENT ON COLUMN tickets.district IS 'Район из входного файла; NULL — не указан';
COMMENT ON COLUMN tickets.address IS 'Адрес выезда из входного файла';
COMMENT ON COLUMN tickets.geom IS 'Точка адреса выезда (WGS84); заявка без координат не загружается';
COMMENT ON COLUMN tickets.window_start IS 'Начало окна, в которое бригада должна прибыть; местное время региона';
COMMENT ON COLUMN tickets.window_end IS 'Конец окна прибытия; местное время региона, строго позже начала';
COMMENT ON COLUMN tickets.duration_min IS 'Время работы на объекте в минутах по нормативу типа работ, без дороги';
COMMENT ON COLUMN tickets.status IS 'Статус заявки; completed и cancelled в перепланировании не участвуют';
COMMENT ON COLUMN tickets.received_at IS 'Момент фактического поступления заявки, местное время региона; от него у аварии отсчитываются норматив выполнения и целевое время реакции';
COMMENT ON COLUMN tickets.cancelled_after_dispatch IS 'Заявку отменили после того, как бригада выехала: выезд уже потрачен и учитывается в метриках';

COMMENT ON TABLE plans IS 'План выездов региона на дату: одна запись — один результат построения или перепланирования';
COMMENT ON COLUMN plans.region_id IS 'Регион, для которого построен план';
COMMENT ON COLUMN plans.plan_date IS 'Дата, на которую составлен план; с ней складывается время смены бригад';
COMMENT ON COLUMN plans.algorithm IS 'Чем построен план: or_tools — основной алгоритм, baseline_fcfs — план для сравнения';
COMMENT ON COLUMN plans.parent_plan_id IS 'План, из которого получен этот перепланированием; NULL — план построен с нуля';
COMMENT ON COLUMN plans.created_at IS 'Момент построения плана, местное время региона; пишется приложением';

COMMENT ON TABLE assignments IS 'Строка плана: одна запись — одна заявка плана, назначенная бригаде или оставшаяся без исполнителя';
COMMENT ON COLUMN assignments.plan_id IS 'План, к которому относится строка';
COMMENT ON COLUMN assignments.ticket_id IS 'Заявка; в одном плане встречается ровно один раз';
COMMENT ON COLUMN assignments.engineer_id IS 'Бригада-исполнитель; NULL — заявка не назначена, причина в unassigned_reason';
COMMENT ON COLUMN assignments.sequence_no IS 'Порядковый номер визита в маршруте бригады, с 1; NULL у неназначенной заявки';
COMMENT ON COLUMN assignments.planned_arrival IS 'Плановое прибытие на заявку, местное время региона, с точностью до минуты; попадает в окно заявки; NULL у неназначенной';
COMMENT ON COLUMN assignments.travel_time_min IS 'Время в пути до заявки от предыдущей точки маршрута по дорожной сети, минуты с округлением вверх; NULL у неназначенной';
COMMENT ON COLUMN assignments.travel_distance_m IS 'Расстояние до заявки от предыдущей точки маршрута, метры по дорожной сети; NULL у неназначенной';
COMMENT ON COLUMN assignments.unassigned_reason IS 'Причина, по которой заявка не назначена; NULL у назначенной';
COMMENT ON COLUMN assignments.explanation IS 'Готовый текст для пользователя: почему заявка назначена этой бригаде или почему не назначена';

COMMENT ON TABLE replan_events IS 'Событие перепланирования: одна запись — одно событие, применённое к плану';
COMMENT ON COLUMN replan_events.plan_id IS 'План, к которому применено событие';
COMMENT ON COLUMN replan_events.event_type IS 'Вид события: новая срочная заявка, новая обычная заявка, отмена заявки, бригада недоступна';
COMMENT ON COLUMN replan_events.payload IS 'Параметры события в том виде, в каком они пришли в запросе';
COMMENT ON COLUMN replan_events.triggered_at IS 'Момент события, местное время региона';
COMMENT ON COLUMN replan_events.result_plan_id IS 'План, полученный после обработки события; NULL — событие не удалось обработать';
"""


def upgrade() -> None:
    """Creates the schema and the two login roles the application and manual
    read-only access use. Role passwords come from the environment of the process
    running the migration and are passed as bind parameters, never as SQL text.
    A role that already exists keeps its name only: its attributes and password are
    reset to these."""
    passwords = {}
    for role, var in (("rw", "APP_RW_PASSWORD"), ("ro", "APP_RO_PASSWORD")):
        value = os.environ.get(var)
        if not value:
            raise RuntimeError(f"{var} is not set: the role password comes from it")
        passwords[role] = value

    op.execute(SCHEMA)

    # `ALTER ROLE ... PASSWORD` takes no bind parameters, so the values travel as
    # transaction-local settings and are quoted by the server.
    op.execute(
        sa.text(
            "SELECT set_config('app.rw_password', :rw, true),"
            " set_config('app.ro_password', :ro, true)"
        ).bindparams(rw=passwords["rw"], ro=passwords["ro"])
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
                CREATE ROLE app_rw LOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_ro') THEN
                CREATE ROLE app_ro LOGIN;
            END IF;
            EXECUTE 'ALTER ROLE app_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
                || ' NOBYPASSRLS PASSWORD ' || quote_literal(current_setting('app.rw_password'));
            EXECUTE 'ALTER ROLE app_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
                || ' NOBYPASSRLS PASSWORD ' || quote_literal(current_setting('app.ro_password'));
        END
        $$;
        """
    )
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_rw")
        op.execute(f"GRANT SELECT ON {table} TO app_ro")


def downgrade() -> None:
    """Drops the schema and the roles. Roles belong to the whole cluster, not to this
    database: in a shared cluster this removes them for every database. The PostGIS
    extension stays: other objects of the database may depend on it."""
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP ROLE IF EXISTS app_ro")
    op.execute("DROP ROLE IF EXISTS app_rw")
