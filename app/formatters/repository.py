def format_repository(payload):
    repo = payload.get("repository") or {}
    name = repo.get("name", "unknown")
    lang = repo.get("language", "не указан")
    private = "private" if repo.get("private") else "public"
    url = repo.get("html_url", "")

    return (
        f"🆕 <b>Новый репозиторий: {name}</b>\n"
        f"🗂 Язык: <code>{lang}</code>\n"
        f"🔒 {private.title()}\n"
        f"🔗 <a href='{url}'>Открыть репозиторий</a>"
    )
