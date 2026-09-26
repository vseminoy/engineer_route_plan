from pathlib import PurePath
from typing import Annotated

import pydantic
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from python_multipart.exceptions import FormParserError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from src.api.deps import get_loader
from src.api.schemas.generated import models as api
from src.errors import InvalidInput
from src.logging import get_logger
from src.service.loader import Loader, LoadResult, Source

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["data"])

LoaderDep = Annotated[Loader, Depends(get_loader)]

_SOURCES: dict[str, Source] = {".csv": "csv", ".json": "json"}
# The form carries `region` and `tickets_file`; one field and one file more still parse,
# so that an extra one is answered as an unknown field of the contract, not a broken form.
_MAX_FORM_FIELDS = 2
_MAX_FORM_FILES = 2
# Bytes of a form field that is not a file; `region` is at most 50 characters.
_MAX_FORM_FIELD_BYTES = 1024


def _result(result: LoadResult) -> api.DataLoadResult:
    return api.DataLoadResult(
        region=api.RegionCode(result.region),
        engineers=result.engineers,
        tickets=result.tickets,
        rows_total=result.rows_total,
        rows_skipped=result.rows_skipped,
        rows_invalid=[
            api.InvalidRow(row=r.row, reason=api.Reason(r.reason), column=r.column)
            for r in result.rows_invalid
        ],
    )


async def _upload(request: Request) -> tuple[api.RegionDataUpload, str]:
    """The form checked against the contract's `RegionDataUpload`, and the file's name.
    Starlette answers a form over the limits with `400` itself, but lets a malformed part
    through as the parser's own error, answered here the same way. The body over the
    request limit is cut off before it is read in full.
    Source: https://www.starlette.io/requests/#request-files (`max_files`, `max_fields`,
    `max_part_size`)."""
    values: dict[str, object] = {}
    filename = ""
    try:
        async with request.form(
            max_files=_MAX_FORM_FILES,
            max_fields=_MAX_FORM_FIELDS,
            max_part_size=_MAX_FORM_FIELD_BYTES,
        ) as form:
            for name, value in form.multi_items():
                if isinstance(value, UploadFile):
                    values[name] = await value.read()
                    if name == "tickets_file":
                        filename = value.filename or ""
                else:
                    values[name] = value
    except FormParserError as e:
        logger.warning("data_upload_failed", reason="form_invalid")
        raise HTTPException(status_code=400) from e
    except HTTPException as e:
        # Starlette's answer to a form over the limits; the body limit's `413` passes as is.
        if e.status_code == 400:
            logger.warning("data_upload_failed", reason="form_invalid")
        raise
    try:
        upload = api.RegionDataUpload.model_validate(values)
    except pydantic.ValidationError as e:
        raise RequestValidationError(
            [{**error, "loc": ("body", *error["loc"])} for error in e.errors(include_url=False)]
        ) from e
    return upload, filename


@router.post("/data/upload", response_model=api.DataLoadResult, operation_id="upload_region_data")
async def upload_region_data(request: Request, loader: LoaderDep) -> api.DataLoadResult:
    upload, filename = await _upload(request)
    region = upload.region.root
    source = _SOURCES.get(PurePath(filename).suffix.lower())
    if source is None:
        # The file name stays out of the log: it may name a person.
        logger.warning("data_upload_failed", reason="file_type_invalid", region=region)
        raise InvalidInput(
            "file_type_invalid", fields=[("tickets_file", "Файл должен быть .csv или .json")]
        )
    # The loader logs its own failures.
    return _result(await loader.load(region, source, upload.tickets_file))


@router.post("/data/demo", response_model=api.DataLoadResult, operation_id="load_demo_data")
async def load_demo_data(body: api.DemoDataRequest, loader: LoaderDep) -> api.DataLoadResult:
    return _result(await loader.load(body.region.root, "demo"))
