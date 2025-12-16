def format_push(payload):
    repo = payload.get("repository", {}).get("full_name", "unknown")
    branch_ref = payload.get("ref", "")
    branch = branch_ref.split("/")[-1] if branch_ref else "unknown"
    commits = payload.get("commits", [])[:3]

    if not commits:
        return f"📌 Новый push в <b>{repo}</b> ({branch})"

    lines = []
    for c in commits:
        msg = (c.get("message") or "")[:80]
        url = c.get("url", "")
        lines.append(f'• <code>{msg}</code>\n  🔗 <a href="{url}">commit</a>')

    return f"📌 <b>Push в {repo}</b> ({branch})\n" + "\n".join(lines)
