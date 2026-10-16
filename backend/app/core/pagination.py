from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PageParams | None:
    """Opt-in pagination: without `page` the endpoint returns its full list as before."""
    return PageParams(page, page_size) if page is not None else None


def _meta(params: PageParams, total: int) -> dict[str, int]:
    return {"page": params.page, "page_size": params.page_size, "total": total}


def paginate_select(
    db: Session, statement: Select, params: PageParams | None
) -> tuple[Sequence[Any], dict[str, int] | None]:
    """Run a scalar select, applying LIMIT/OFFSET and a COUNT when paginating."""
    if params is None:
        return db.scalars(statement).all(), None
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = db.scalars(statement.offset(params.offset).limit(params.page_size)).all()
    return rows, _meta(params, total or 0)


def paginate_list[T](
    items: Sequence[T], params: PageParams | None
) -> tuple[Sequence[T], dict[str, int] | None]:
    if params is None:
        return items, None
    return items[params.offset : params.offset + params.page_size], _meta(params, len(items))


def page_response(data: list, meta: dict[str, int] | None) -> dict[str, Any]:
    """`data` stays a list either way; `pagination` is added only when paginating."""
    return {"data": data} if meta is None else {"data": data, "pagination": meta}
