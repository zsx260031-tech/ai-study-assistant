import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "records.db")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
LANGUAGES = ("python", "cpp", "javascript")
MAX_HISTORY = 12

SYSTEM_PROMPT = (
    "你是一名计算机专业课辅导老师，擅长把抽象概念讲得具体、准确。"
    "你只输出 JSON，不要输出任何其他文字。"
    "JSON 结构必须严格为："
    '{"definition": "string", "analogy": "string", "code": "string", '
    '"pitfalls": ["string", "string", "string"], '
    '"quiz": [{"question": "string", "type": "choice", "options": ["string"], "answer": "string", "explanation": "string"}, '
    '{"question": "string", "type": "short", "answer": "string", "explanation": "string"}]}。'
    "definition 不超过 60 字；analogy 不超过 100 字，使用日常生活场景；"
    "code 不超过 25 行、必须可以直接运行、包含最小可运行的输入与输出；"
    "pitfalls 固定 3 条，每条不超过 40 字；"
    "quiz 固定 3 题，其中 2 题 choice（必须有 4 个 options，answer 写选项字母）和 1 题 short，explanation 不超过 80 字。"
)

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "concept TEXT NOT NULL, "
        "language TEXT NOT NULL, "
        "payload TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()


def call_model(concept, language):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请先设置环境变量")
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请讲解概念：%s。示例代码使用 %s。" % (concept, language)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    raw_body = json.dumps(body).encode("utf-8")
    last_error = None
    for _ in range(2):
        req = urllib.request.Request(API_URL, data=raw_body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + key)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8")
            content = json.loads(raw)["choices"][0]["message"]["content"]
            return json.loads(content)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = ""
            last_error = "HTTP %s %s" % (exc.code, detail[:200])
            time.sleep(1)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError("调用模型失败：%s" % last_error)


def clean_option(text):
    return re.sub(r"^[A-Da-d][.、．)）]\s*", "", text)


def normalize(payload):
    if not isinstance(payload, dict):
        payload = {}
    pitfalls = payload.get("pitfalls")
    if not isinstance(pitfalls, list):
        pitfalls = []
    quiz = payload.get("quiz")
    if not isinstance(quiz, list):
        quiz = []
    clean_quiz = []
    for item in quiz[:3]:
        if not isinstance(item, dict):
            continue
        options = item.get("options")
        clean_quiz.append(
            {
                "question": str(item.get("question", "")),
                "type": "choice" if isinstance(options, list) and options else "short",
                "options": [clean_option(str(x)) for x in options] if isinstance(options, list) else [],
                "answer": str(item.get("answer", "")),
                "explanation": str(item.get("explanation", "")),
            }
        )
    return {
        "definition": str(payload.get("definition", "")),
        "analogy": str(payload.get("analogy", "")),
        "code": str(payload.get("code", "")),
        "pitfalls": [str(x) for x in pitfalls[:3]],
        "quiz": clean_quiz,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/generate")
def generate():
    data = request.get_json(silent=True) or {}
    concept = (data.get("concept") or "").strip()
    language = data.get("language") or "python"
    if not concept:
        return jsonify({"ok": False, "error": "请输入要学习的概念"}), 400
    if len(concept) > 50:
        return jsonify({"ok": False, "error": "概念名称请控制在 50 字以内"}), 400
    if language not in LANGUAGES:
        language = "python"
    try:
        result = call_model(concept, language)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    payload = normalize(result)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    db = get_db()
    cur = db.execute(
        "INSERT INTO records (concept, language, payload, created_at) VALUES (?, ?, ?, ?)",
        (concept, language, json.dumps(payload, ensure_ascii=False), created_at),
    )
    db.commit()
    return jsonify(
        {
            "ok": True,
            "id": cur.lastrowid,
            "concept": concept,
            "language": language,
            "created_at": created_at,
            "data": payload,
        }
    )


@app.get("/api/history")
def history():
    rows = get_db().execute(
        "SELECT id, concept, language, created_at FROM records ORDER BY id DESC LIMIT ?",
        (MAX_HISTORY,),
    ).fetchall()
    return jsonify({"ok": True, "items": [dict(row) for row in rows]})


@app.get("/api/record/<int:record_id>")
def record(record_id):
    row = get_db().execute(
        "SELECT id, concept, language, payload, created_at FROM records WHERE id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify(
        {
            "ok": True,
            "id": row["id"],
            "concept": row["concept"],
            "language": row["language"],
            "created_at": row["created_at"],
            "data": json.loads(row["payload"]),
        }
    )


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
