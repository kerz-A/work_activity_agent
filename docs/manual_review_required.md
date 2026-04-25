  
  \- manual\_review\_required

5\. Task relevance:  
  \- high  
  \- medium  
  \- low  
  \- unclear

6\. Risk flags:  
  \- static\_screen\_long\_period  
  \- unrelated\_website  
  \- job\_search\_site  
  \- freelance\_platform  
  \- other\_project\_tool  
  \- personal\_messenger  
  \- entertainment\_content  
  \- low\_task\_relevance  
  \- sensitive\_data\_detected  
  \- manual\_review\_required

7\. Timeline analysis:  
  \- do not judge a single screenshot alone  
  \- detect repeated patterns across intervals  
  \- compare with task context and actual result if available

8\. Reports:  
  \- screenshot-level table  
  \- employee daily summary  
  \- project-level summary  
  \- risk episodes  
  \- manager review queue  
  \- recommendations for manual verification

\#\# Output wording rules

Bad:  
\- "Employee is farming time."  
\- "Employee is looking for a job."  
\- "Employee is guilty."

Good:  
\- "Detected screenshots with low task relevance."  
\- "A job-search website is visible in 5 screenshots during the tracked interval."  
\- "Manual review is required before any conclusion."  
---

# **7\. MCP config sketch for Codex**

Примерно так, если подключать локально:

\[mcp\_servers.filesystem\]  
command \= "npx"  
args \= \["-y", "@modelcontextprotocol/server-filesystem", "/secure/apptask-data"\]

\[mcp\_servers.playwright\]  
command \= "npx"  
args \= \["-y", "@playwright/mcp"\]

\[mcp\_servers.github\]  
command \= "docker"  
args \= \["run", "-i", "--rm", "-e", "GITHUB\_PERSONAL\_ACCESS\_TOKEN", "ghcr.io/github/github-mcp-server"\]

\[mcp\_servers.google\_sheets\]  
command \= "node"  
args \= \["/path/to/google-sheets-mcp/server.js"\]

Для GitHub лучше включать только нужные toolsets, например `repos,issues,pull_requests,actions`, чтобы снизить риск лишнего доступа и размер контекста. Официальный GitHub MCP поддерживает настройку toolsets и отдельных tools.

---

# **8\. Что не советую брать как основу**

| Компонент | Почему осторожно |
| ----- | ----- |
| Screen Monitor | Дублирует мониторинг AppTask и может восприниматься как дополнительная скрытая слежка |
| Native Devtools | Сильный desktop automation, но для анализа уже собранных скринов избыточен |
| Google Cloud Vision | Хороший OCR, но скрины сотрудников лучше сначала redaction/local processing |
| Slack history ingestion | Может затянуть личные/чувствительные переписки в анализ |
| Любой MCP с write/delete правами | Для такого агента нужен read-only by default |

Screen Monitor поддерживает continuous screen monitoring 2–5 FPS и OCR, а Native Devtools умеет capture screenshots, OCR, mouse/keyboard simulation и window management. Для вашего сценария это слишком мощные инструменты, если AppTask уже собирает скриншоты; их лучше использовать только для тестового стенда, а не для дополнительного мониторинга сотрудников.

---

# **9\. Практичная финальная сборка**

Я бы делал так:

Codex Skill:  
\- work-activity-screenshot-analysis

MCP:  
\- filesystem  
\- playwright, если надо забирать из AppTask UI  
\- github или gitlab  
\- atlassian/jira, если задачи в Jira  
\- figma, если есть дизайнеры  
\- google sheets  
\- optional slack только для уведомлений

Python services:  
\- apptask\_collector.py  
\- screenshot\_normalizer.py  
\- ocr\_runner.py  
\- presidio\_redactor.py  
\- classifier.py  
\- timeline\_detector.py  
\- risk\_score.py  
\- report\_writer.py

## **Таблица выбора**

| Если нужно | Брать |
| ----- | ----- |
| Быстро проверить идею | Image OCR Toolkit \+ Google Sheets |
| Скачать скрины из AppTask UI | Playwright MCP |
| Массово OCR‑ить архивы | Image OCR Toolkit |
| Локально OCR‑ить на macOS | Vision OCR MCP |
| Маскировать PII на изображениях | Presidio Image Redactor |
| Делать отчёт с evidence/timeline | Agent Evidence MCP |
| Сверять разработчиков с результатом | GitHub/GitLab MCP |
| Сверять дизайнеров с макетами | Figma MCP |
| Сверять задачи | AppTask export или Jira MCP |
| Отчёты менеджеру | Google Sheets MCP / skill |

---

# **10\. Итог**

Готового «AppTask Screenshot Activity Agent» я не нашёл. Реалистичная сборка:

1\. Codex skill — описывает правила анализа и guardrails.  
2\. Playwright MCP или кастомный collector — забирает данные из AppTask.  
3\. Image OCR Toolkit / Vision OCR — оцифровывает скриншоты.  
4\. Presidio / Nutrient — маскирует чувствительные данные.  
5\. Custom classifier — классифицирует activity\_type и relevance.  
6\. Timeline detector — ищет повторяющиеся аномалии.  
7\. GitHub/GitLab/Figma/Jira MCP — добавляет контекст фактического результата.  
8\. Google Sheets / dashboard — отдаёт отчёт менеджеру.  
9\. Human review — обязательный финальный слой.

Самый правильный MVP:

AppTask export  
→ Image OCR Toolkit  
→ Presidio redaction  
→ custom Codex skill  
→ Google Sheets report  
→ manager review

А уже потом подключать Playwright, GitHub/GitLab, Figma и Jira.

