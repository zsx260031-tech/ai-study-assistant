const form = document.getElementById("ask-form");
const conceptInput = document.getElementById("concept");
const languageSelect = document.getElementById("language");
const submitBtn = document.getElementById("submit-btn");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const historyList = document.getElementById("history");
const refreshBtn = document.getElementById("refresh-btn");

const LANGUAGE_LABELS = { python: "Python", cpp: "C++", javascript: "JavaScript" };

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(text).replace(/[&<>"']/g, function (ch) {
    return map[ch];
  });
}

function setStatus(text, isError) {
  if (!text) {
    statusBox.classList.add("hidden");
    return;
  }
  statusBox.textContent = text;
  statusBox.classList.toggle("error", Boolean(isError));
  statusBox.classList.remove("hidden");
}

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.textContent = loading ? "生成中…" : "生成讲解";
}

function renderQuizItem(item, index) {
  let options = "";
  if (item.options.length > 0) {
    options =
      '<ul class="quiz-options">' +
      item.options
        .map(function (opt, optIndex) {
          return (
            '<li><span class="opt-letter">' +
            String.fromCharCode(65 + optIndex) +
            ".</span> " +
            escapeHtml(opt) +
            "</li>"
          );
        })
        .join("") +
      "</ul>";
  }
  return (
    '<div class="quiz-item">' +
    '<p class="quiz-question">' +
    (index + 1) +
    ". " +
    escapeHtml(item.question) +
    "</p>" +
    options +
    '<button type="button" class="answer-toggle">显示答案</button>' +
    '<div class="answer-box hidden">' +
    "<p><strong>参考答案：</strong>" +
    escapeHtml(item.answer) +
    "</p>" +
    "<p><strong>解析：</strong>" +
    escapeHtml(item.explanation) +
    "</p>" +
    "</div>" +
    "</div>"
  );
}

function renderResult(record) {
  const data = record.data;
  const pitfalls = data.pitfalls
    .map(function (item) {
      return "<li>" + escapeHtml(item) + "</li>";
    })
    .join("");
  const quiz = data.quiz.map(renderQuizItem).join("");
  resultBox.innerHTML =
    '<div class="result-head">' +
    "<h2>" +
    escapeHtml(record.concept) +
    "</h2>" +
    '<span class="meta">' +
    LANGUAGE_LABELS[record.language] +
    " · " +
    escapeHtml(record.created_at) +
    "</span>" +
    "</div>" +
    '<article class="card"><h3>一句话定义</h3><p>' +
    escapeHtml(data.definition) +
    "</p></article>" +
    '<article class="card analogy"><h3>生活类比</h3><p>' +
    escapeHtml(data.analogy) +
    "</p></article>" +
    '<article class="card code-card"><h3>最小示例</h3><pre><code>' +
    escapeHtml(data.code) +
    "</code></pre></article>" +
    '<article class="card"><h3>常见误区</h3><ul class="pitfalls">' +
    pitfalls +
    "</ul></article>" +
    '<article class="card"><h3>自测题</h3>' +
    quiz +
    "</article>";
  resultBox.classList.remove("hidden");
  resultBox.querySelectorAll(".answer-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const box = btn.nextElementSibling;
      box.classList.toggle("hidden");
      btn.textContent = box.classList.contains("hidden") ? "显示答案" : "收起答案";
    });
  });
}

async function ask(concept) {
  setLoading(true);
  setStatus("正在调用大模型生成讲解，通常需要 5–15 秒…", false);
  try {
    const resp = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept: concept, language: languageSelect.value }),
    });
    const payload = await resp.json();
    if (!payload.ok) {
      throw new Error(payload.error || "生成失败");
    }
    setStatus("", false);
    renderResult(payload);
    loadHistory();
    resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus("出错了：" + err.message, true);
  } finally {
    setLoading(false);
  }
}

async function loadHistory() {
  try {
    const resp = await fetch("/api/history");
    const payload = await resp.json();
    if (!payload.ok) {
      return;
    }
    if (payload.items.length === 0) {
      historyList.innerHTML = '<li class="empty">还没有学习记录</li>';
      return;
    }
    historyList.innerHTML = payload.items
      .map(function (item) {
        return (
          '<li class="history-item" data-id="' +
          item.id +
          '">' +
          '<span class="history-concept">' +
          escapeHtml(item.concept) +
          "</span>" +
          '<span class="history-meta">' +
          LANGUAGE_LABELS[item.language] +
          " · " +
          escapeHtml(item.created_at) +
          "</span>" +
          "</li>"
        );
      })
      .join("");
    historyList.querySelectorAll(".history-item").forEach(function (li) {
      li.addEventListener("click", function () {
        loadRecord(li.dataset.id);
      });
    });
  } catch (err) {
    historyList.innerHTML = '<li class="empty">历史加载失败</li>';
  }
}

async function loadRecord(id) {
  try {
    const resp = await fetch("/api/record/" + id);
    const payload = await resp.json();
    if (!payload.ok) {
      throw new Error(payload.error || "加载失败");
    }
    renderResult(payload);
    setStatus("", false);
    resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus("出错了：" + err.message, true);
  }
}

form.addEventListener("submit", function (event) {
  event.preventDefault();
  const concept = conceptInput.value.trim();
  if (!concept) {
    setStatus("请先输入一个概念", true);
    conceptInput.focus();
    return;
  }
  ask(concept);
});

refreshBtn.addEventListener("click", loadHistory);
loadHistory();
