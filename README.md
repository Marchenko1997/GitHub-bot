# 🤖 GitHub → Telegram Webhook Bot

This bot receives GitHub events (push, pull request, repository creation)  
and sends structured notifications to Telegram.

---

## 🚀 Bot Features

### 🔧 Push Events
- Repository name  
- Branch name  
- Up to 3 latest commits  
- Commit links  

### 📝 Pull Request Events
- PR opened  
- PR closed  
- PR merged  

### 🆕 Repository Creation Events
- Repository name  
- Type (public/private)  
- Language  
- Repository link  

---

## 🧩 Technologies Used

| Technology | Purpose |
|-----------|---------|
| **FastAPI** | Handles GitHub webhook events |
| **Aiogram** | Sends messages to Telegram |
| **Uvicorn** | ASGI server |
| **python-dotenv** | Loads environment variables |
| **ngrok** | Exposes local server to the internet |
| **Poetry** | Dependency management |

---

## 🚀 Running the Project

### 1️⃣ Install dependencies
```bash
poetry install
```

### 2️⃣ Activate virtual environment
```bash
poetry shell
```

### 3️⃣ Start the FastAPI server
```bash
uvicorn app.main:app --reload --port 8000
```

### 4️⃣ Start ngrok
```bash
ngrok http 8000
```

---

## 🌐 Configure GitHub Webhook

Copy the generated URL:

```
https://xxxxx.ngrok-free.dev/github-webhook
```

Then paste it here:

GitHub → **Settings → Webhooks → Payload URL**

---

## 📦 Environment Variables

Create `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
GITHUB_WEBHOOK_SECRET=your_secret
```

---

## ✅ Done!

Now your bot will receive GitHub webhook events and send them to Telegram 🎉