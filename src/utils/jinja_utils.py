import arrow


def humanize_timestamp(value: float | None, fmt="YYYY-MM-DD HH:mm:ss", tz="local"):
    if value is None:
        return ""

    try:
        dt = arrow.get(float(value))
        if tz:
            dt = dt.to(tz)

        return dt.format(fmt)
    except Exception:
        return str(value)
