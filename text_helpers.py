import json


def load_json_dict(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_cached_json(context, cache_key: str, path: str) -> dict:
    data = context.application.bot_data.get(cache_key)
    if data is None:
        data = load_json_dict(path)
        context.application.bot_data[cache_key] = data
    return data


def split_chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i:i + size]
