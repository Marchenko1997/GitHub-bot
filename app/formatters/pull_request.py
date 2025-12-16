def format_pr(payload):
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository", {}).get("full_name", "")

    title = (pr.get("title") or "")[:100]
    number = pr.get("number")
    url = pr.get("html_url")

    if action == "opened":
        prefix = "📝 Открыт PR"
    elif action == "closed" and pr.get("merged"):
        prefix = "✅ Смёржен PR"
    elif action == "closed":
        prefix = "🛑 Закрыт PR"
    else:
        return None

    return (
        f"{prefix} #{number} в <code>{repo}</code>\n"
        f"{title}\n"
        f'🔗 <a href="{url}">Открыть PR</a>'
    )
