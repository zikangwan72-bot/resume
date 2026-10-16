from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status


def _is_empty_value(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


def _form_data_error(message: str, field_id: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "invalid_form_data", "message": message, "field_id": field_id},
    )


def _validate_form_data(form_data: dict, form_schema: dict) -> None:
    fields = form_schema.get("fields") if isinstance(form_schema, dict) else None
    if not isinstance(fields, list):
        raise _form_data_error("流程表单定义无效")
    field_definitions: dict[str, dict] = {}
    for field in fields:
        if not isinstance(field, dict):
            raise _form_data_error("流程表单定义无效")
        field_id = field.get("id", field.get("key"))
        field_type = field.get("type")
        if not isinstance(field_id, str) or not field_id.strip() or field_type == "section":
            continue
        field_definitions[field_id] = field
    for field_id in form_data:
        if field_id not in field_definitions:
            raise _form_data_error("提交了未定义字段", field_id)
    for field_id, field in field_definitions.items():
        _validate_field_value(field, form_data.get(field_id), field_id)


def _validate_field_value(field: dict, value: object, field_id: str) -> None:
    label = field.get("label", field_id)
    field_type = field.get("type")
    if field.get("required") and _is_empty_value(value):
        raise _form_data_error(f"请填写：{label}", field_id)
    if _is_empty_value(value):
        return
    if field_type in {"number", "money"}:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _form_data_error(f"{label}必须是数字", field_id)
        _validate_numeric_value(value, field, field_id, label)
    elif field_type in {"text", "textarea", "user", "department"}:
        if not isinstance(value, str):
            raise _form_data_error(f"{label}格式不正确", field_id)
    elif field_type == "date":
        _validate_date(value, field_id, label)
    elif field_type == "date_range":
        _validate_date_range(value, field_id, label)
    elif field_type in {"radio", "select"}:
        _validate_option(value, field, field_id, label)
    elif field_type == "checkbox":
        if not isinstance(value, list):
            raise _form_data_error(f"{label}必须是列表", field_id)
        for option in value:
            _validate_option(option, field, field_id, label)
    elif field_type == "attachment":
        if not isinstance(value, str) and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            raise _form_data_error(f"{label}格式不正确", field_id)
    elif field_type == "detail_table":
        _validate_detail_table(value, field, field_id, label)
    else:
        raise _form_data_error(f"{label}字段类型不受支持", field_id)


def _validate_option(value: object, field: dict, field_id: str, label: object) -> None:
    options = field.get("options")
    if not _valid_choice_options(options):
        raise _form_data_error(f"{label}选项配置无效", field_id)
    if not any(type(value) is type(option) and value == option for option in options):
        raise _form_data_error(f"{label}选项无效", field_id)


def _valid_choice_options(options: object) -> bool:
    if not isinstance(options, list) or not options:
        return False

    seen: set[tuple[type, object]] = set()
    for option in options:
        if not isinstance(option, str | int | float | bool):
            return False
        if isinstance(option, str) and not option.strip():
            return False
        key = (type(option), option)
        if key in seen:
            return False
        seen.add(key)
    return True


def _validate_date(value: object, field_id: str, label: object) -> date:
    if not isinstance(value, str):
        raise _form_data_error(f"{label}必须是日期", field_id)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _form_data_error(f"{label}日期格式不正确", field_id) from exc


def _validate_date_range(value: object, field_id: str, label: object) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise _form_data_error(f"{label}必须包含开始和结束日期", field_id)
    start = _validate_date(value[0], field_id, label)
    end = _validate_date(value[1], field_id, label)
    if start > end:
        raise _form_data_error(f"{label}结束日期不能早于开始日期", field_id)


def _validate_numeric_value(value: int | float, field: dict, field_id: str, label: object) -> None:
    minimum, maximum, precision = field.get("min"), field.get("max"), field.get("precision")
    if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int | float)):
        raise _form_data_error(f"{label}数值配置无效", field_id)
    if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int | float)):
        raise _form_data_error(f"{label}数值配置无效", field_id)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise _form_data_error(f"{label}数值配置无效", field_id)
    if precision is not None and (
        not isinstance(precision, int) or isinstance(precision, bool) or not 0 <= precision <= 6
    ):
        raise _form_data_error(f"{label}数值配置无效", field_id)
    if minimum is not None and value < minimum:
        raise _form_data_error(f"{label}不能小于最小值", field_id)
    if maximum is not None and value > maximum:
        raise _form_data_error(f"{label}不能大于最大值", field_id)
    if precision is not None:
        try:
            places = max(0, -Decimal(str(value)).as_tuple().exponent)
        except (InvalidOperation, ValueError) as exc:
            raise _form_data_error(f"{label}必须是数字", field_id) from exc
        if places > precision:
            raise _form_data_error(f"{label}最多保留 {precision} 位小数", field_id)


def _validate_detail_table(value: object, field: dict, field_id: str, label: object) -> None:
    if not isinstance(value, list):
        raise _form_data_error(f"{label}必须是明细行列表", field_id)
    columns = field.get("columns")
    if not isinstance(columns, list):
        raise _form_data_error(f"{label}列定义无效", field_id)
    column_definitions: dict[str, dict] = {}
    for column in columns:
        if not isinstance(column, dict):
            raise _form_data_error(f"{label}列定义无效", field_id)
        column_id = column.get("id", column.get("key"))
        if not isinstance(column_id, str) or not column_id.strip():
            raise _form_data_error(f"{label}列定义无效", field_id)
        if column_id in column_definitions:
            raise _form_data_error(f"{label}列定义无效", field_id)
        if not isinstance(column.get("label"), str) or not column["label"].strip():
            raise _form_data_error(f"{label}列定义无效", field_id)
        if column.get("type") not in {"text", "number", "money", "date", "select"}:
            raise _form_data_error(f"{label}列定义无效", field_id)
        if not isinstance(column.get("required", False), bool):
            raise _form_data_error(f"{label}列定义无效", field_id)
        column_definitions[column_id] = column
    for row_index, row in enumerate(value):
        row_field_id = f"{field_id}.{row_index}"
        if not isinstance(row, dict):
            raise _form_data_error(f"{label}每行必须是对象", row_field_id)
        for column_id in row:
            if column_id not in column_definitions:
                raise _form_data_error("提交了未定义明细字段", f"{row_field_id}.{column_id}")
        for column_id, column in column_definitions.items():
            _validate_field_value(column, row.get(column_id), f"{row_field_id}.{column_id}")
