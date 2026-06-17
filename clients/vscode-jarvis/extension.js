// JARVIS Coding Agent — VS Code IDE-міст (CA-6.3).
//
// Тонкий клієнт поверх tools REST `/agent/code/edit` (inline-diff propose, dry-run) і
// `/agent/code/review`. Бізнес-логіки тут немає (S3) — лише представлення: показати diff
// у нативному VS Code diff-view і за згодою застосувати запропонований вміст.
"use strict";

const vscode = require("vscode");
const http = require("http");
const https = require("https");
const { URL } = require("url");

function cfg() {
  const c = vscode.workspace.getConfiguration("jarvis");
  return {
    baseUrl: String(c.get("toolsUrl") || "http://127.0.0.1:8001").replace(/\/+$/, ""),
    apiKey: String(c.get("apiKey") || ""),
    userId: Number(c.get("userId") || 0),
  };
}

// POST JSON → Promise<object>. Без зовнішніх залежностей (node http/https).
function postJSON(baseUrl, path, body, apiKey) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(baseUrl + path);
    } catch (e) {
      return reject(new Error("Невалідний jarvis.toolsUrl: " + baseUrl));
    }
    const payload = Buffer.from(JSON.stringify(body), "utf8");
    const headers = { "Content-Type": "application/json", "Content-Length": payload.length };
    if (apiKey) headers["Authorization"] = "Bearer " + apiKey;
    const lib = u.protocol === "https:" ? https : http;
    const req = lib.request(
      { hostname: u.hostname, port: u.port, path: u.pathname + u.search, method: "POST", headers },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 400) {
            return reject(new Error("HTTP " + res.statusCode + ": " + data.slice(0, 300)));
          }
          try {
            resolve(JSON.parse(data || "{}"));
          } catch (e) {
            reject(new Error("Невалідний JSON у відповіді"));
          }
        });
      }
    );
    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

// Показати запропонований вміст у diff-view проти поточного файлу через
// readonly-документ у памʼяті (provider схеми `jarvis-proposed`).
const proposedStore = new Map(); // uri.path → proposed content

async function proposeEdit() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("JARVIS: відкрий файл у редакторі.");
    return;
  }
  const instruction = await vscode.window.showInputBox({
    prompt: "Що змінити у цьому файлі?",
    placeHolder: "напр. додай docstring до функції foo",
  });
  if (!instruction) return;

  const { baseUrl, apiKey, userId } = cfg();
  const doc = editor.document;
  const content = doc.getText();
  const relPath = vscode.workspace.asRelativePath(doc.uri);

  let result;
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS пропонує правку…" },
    async () => {
      result = await postJSON(
        baseUrl,
        "/agent/code/edit",
        { user_id: userId, path: relPath, instruction, content },
        apiKey
      );
    }
  );

  if (!result || !result.changed) {
    vscode.window.showInformationMessage("JARVIS: змін не запропоновано.");
    return;
  }

  const proposedUri = vscode.Uri.parse("jarvis-proposed:" + doc.uri.path);
  proposedStore.set(doc.uri.path, String(result.proposed || ""));
  await vscode.commands.executeCommand(
    "vscode.diff",
    doc.uri,
    proposedUri,
    "JARVIS: " + relPath + " (запропоновано)"
  );

  const pick = await vscode.window.showInformationMessage(
    "Застосувати запропоновану правку?",
    "Apply",
    "Cancel"
  );
  if (pick === "Apply") {
    const edit = new vscode.WorkspaceEdit();
    const full = new vscode.Range(doc.positionAt(0), doc.positionAt(content.length));
    edit.replace(doc.uri, full, String(result.proposed || ""));
    await vscode.workspace.applyEdit(edit);
    vscode.window.showInformationMessage("JARVIS: правку застосовано.");
  }
}

async function reviewDiff() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("JARVIS: відкрий файл/diff у редакторі.");
    return;
  }
  const { baseUrl, apiKey, userId } = cfg();
  let result;
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "JARVIS рев'ю diff…" },
    async () => {
      result = await postJSON(
        baseUrl,
        "/agent/code/review",
        { user_id: userId, diff: editor.document.getText() },
        apiKey
      );
    }
  );
  const verdict = (result && result.verdict) || "?";
  const findings = (result && result.findings) || [];
  const lines = ["verdict: " + verdict + " — " + ((result && result.summary) || "")];
  for (const f of findings) {
    lines.push(`  [${f.severity}] ${f.file}:${f.line} ${f.comment}`);
  }
  const out = vscode.window.createOutputChannel("JARVIS Review");
  out.clear();
  out.appendLine(lines.join("\n"));
  out.show(true);
}

function activate(context) {
  // readonly provider для запропонованого вмісту (праворуч у diff).
  const provider = {
    provideTextDocumentContent(uri) {
      return proposedStore.get(uri.path) || "";
    },
  };
  context.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider("jarvis-proposed", provider),
    vscode.commands.registerCommand("jarvis.proposeEdit", proposeEdit),
    vscode.commands.registerCommand("jarvis.reviewDiff", reviewDiff)
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
