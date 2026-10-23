"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => Array.from(document.querySelectorAll(s));
let token =
  location.hash.slice(1) || sessionStorage.getItem("vc-session") || "";
if (token) {
  sessionStorage.setItem("vc-session", token);
  history.replaceState(null, "", location.pathname);
}
let source = "",
  cues = [],
  strategy = "standard",
  directory = ".",
  currentJob = "",
  detail = null,
  originalUrl = "",
  outputUrl = "",
  polling = false;
let filesMap = new Map(),
  toastTimer,
  uploading = false;
const stageNames = {
  queued: "排队等待",
  preparing: "检查素材",
  prepared: "准备完成",
  model: "AI 分析内容",
  planned: "剪辑计划完成",
  rendering: "渲染与质量检查",
  completed: "完成",
  failed: "执行失败",
  interrupted: "任务已中断",
};
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function toast(text, error = false) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  $("#status-text").textContent = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(
    () => ($("#toast").hidden = true),
    error ? 9000 : 4500,
  );
}
async function api(path, body, raw) {
  const opt = { headers: { "X-Video-Clips-Token": token } };
  if (body !== undefined) {
    opt.method = "POST";
    opt.body = raw ? body : JSON.stringify(body);
    if (!raw) opt.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, opt);
  let data;
  try {
    data = await res.json();
  } catch {
    throw Error("本地服务返回异常，请检查终端。");
  }
  if (!res.ok) throw Error(data.error || "操作失败");
  return data;
}
function mediaUrl(path) {
  return "/api/media?" + new URLSearchParams({ path, token });
}
function artifact(kind) {
  return (
    "/api/artifact?" + new URLSearchParams({ id: currentJob, kind, token })
  );
}
function time(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return (
    String(Math.floor(s / 60)).padStart(2, "0") +
    ":" +
    String(s % 60).padStart(2, "0")
  );
}
function stamp(ms) {
  return (ms / 1000).toFixed(3);
}
function switchVideo(mode) {
  const target = mode === "output" ? outputUrl : originalUrl;
  if (!target) return;
  $("#player").src = target;
  $("#preview-empty").hidden = true;
  $("#view-source").classList.toggle("selected", mode === "source");
  $("#view-output").classList.toggle("selected", mode === "output");
  $("#preview-title").textContent = mode === "source" ? "素材预览" : "成片预览";
}
function selectSource(path) {
  source = path;
  originalUrl = mediaUrl(path);
  $("#source-label").textContent = path.split("/").pop();
  switchVideo("source");
  $$(".file-row").forEach((n) =>
    n.classList.toggle("selected", n.dataset.path === path),
  );
  toast("已选择视频；再选择 SRT 或带时间戳的 ASR 结果。");
}
function syncSelect(selector, items, label) {
  const select = $(selector),
    old = select.value;
  select.replaceChildren(el("option", "", label));
  select.firstChild.value = "";
  for (const item of items) {
    const o = el("option", "", item.name);
    o.value = item.path;
    select.append(o);
  }
  if (items.some((i) => i.path === old)) select.value = old;
}
async function loadFiles(folder = directory) {
  const data = await api(
    "/api/files?" + new URLSearchParams({ directory: folder }),
  );
  directory = data.directory;
  $("#files").replaceChildren();
  $("#breadcrumb").replaceChildren();
  if (directory !== ".") {
    const up = el("button", "", "←");
    up.onclick = () =>
      loadFiles(
        directory.includes("/")
          ? directory.slice(0, directory.lastIndexOf("/"))
          : ".",
      ).catch((e) => toast(e.message, true));
    $("#breadcrumb").append(up);
  }
  $("#breadcrumb").append(
    el("span", "", directory === "." ? "工作目录" : directory),
  );
  for (const file of data.files) {
    filesMap.set(file.path, file);
    const row = el(
      "button",
      "file-row" + (source === file.path ? " selected" : ""),
    );
    row.dataset.path = file.path;
    row.title = file.path;
    const icon = file.directory
      ? "▣"
      : file.suffix === ".srt"
        ? "T"
        : file.suffix === ".json"
          ? "{}"
          : /\.(wav|mp3|ogg|opus|m4a)$/.test(file.path)
            ? "♫"
            : "▶";
    row.append(el("span", "file-icon", icon));
    const meta = el("span", "file-meta");
    meta.append(
      el("strong", "", file.name),
      el(
        "small",
        "",
        file.directory
          ? "文件夹"
          : file.suffix.slice(1).toUpperCase() +
              " · " +
              (file.size / 1048576).toFixed(1) +
              " MB",
      ),
    );
    row.append(meta);
    row.onclick = () => {
      if (file.directory)
        loadFiles(file.path).catch((e) => toast(e.message, true));
      else if (file.suffix === ".srt" || file.suffix === ".json")
        loadTranscript(file.path).catch((e) => toast(e.message, true));
      else if (/\.(mp4|mov|mkv|webm|m4v|avi)$/.test(file.path))
        selectSource(file.path);
      else toast("已发现音频；可在右侧背景音乐中选择。");
    };
    $("#files").append(row);
  }
  const all = [...filesMap.values()].filter((f) => !f.directory);
  syncSelect(
    "#music-select",
    all.filter((f) => /\.(wav|mp3|ogg|opus|m4a)$/.test(f.path)),
    "不添加",
  );
  syncSelect(
    "#response-select",
    all.filter((f) => f.suffix === ".json"),
    "选择 Agent 决策 JSON",
  );
  if (!data.files.length)
    $("#files").append(el("div", "empty-small", "暂无素材，点击 ＋ 导入。"));
}
async function loadTranscript(path) {
  try {
    const data = await api("/api/transcript", { path });
    cues = data.cues;
    $("#transcript-label").textContent =
      cues.length + " 句 · " + path.split("/").pop();
    renderCues();
    showTab("transcript");
    toast("已导入 " + cues.length + " 条带时间戳的字幕。");
  } catch (e) {
    if (path.endsWith(".json")) {
      $("#provider-mode").value = "offline";
      providerMode();
      $("#response-select").value = path;
      toast("该 JSON 无法作为转写导入，已选为 AI 决策文件；执行时会严格校验。");
    } else throw e;
  }
}
function renderCues() {
  $("#cues").replaceChildren();
  cues.forEach((cue, i) => {
    const row = el("div", "cue-row");
    row.append(el("span", "cue-index", String(i + 1).padStart(2, "0")));
    const times = el("div", "cue-times");
    for (const [field, value] of [
      ["start_ms", cue.start_ms],
      ["duration_ms", cue.duration_ms],
    ]) {
      const n = el("input");
      n.type = "number";
      n.min = field === "start_ms" ? "0" : "0.001";
      n.step = "0.001";
      n.value = stamp(value);
      n.setAttribute(
        "aria-label",
        (field === "start_ms" ? "开始秒数 " : "持续秒数 ") + (i + 1),
      );
      n.title = field === "start_ms" ? "开始时间 / 秒" : "持续时间 / 秒";
      n.onchange = () => (cue[field] = Math.round(Number(n.value) * 1000));
      times.append(n);
    }
    row.append(times);
    const text = el("textarea");
    text.value = cue.text;
    text.rows = 1;
    text.setAttribute("aria-label", "字幕 " + (i + 1));
    text.oninput = () => (cue.text = text.value);
    row.append(text);
    row.ondblclick = () => {
      $("#player").currentTime = cue.start_ms / 1000;
    };
    $("#cues").append(row);
  });
}
function showTab(name) {
  $("#cues").hidden = name !== "transcript";
  $("#review-list").hidden = name !== "review";
  $("#tab-transcript").classList.toggle("active", name === "transcript");
  $("#tab-review").classList.toggle("active", name === "review");
  $("#apply-review").hidden = name !== "review" || !detail?.review;
}
function providerMode() {
  const offline = $("#provider-mode").value === "offline";
  $("#remote-fields").hidden = offline;
  $("#offline-fields").hidden = !offline;
}
async function uploadFiles(list) {
  if (uploading) return;
  uploading = true;
  $("#upload").disabled = true;
  try {
    for (const file of list) {
      toast("正在导入 " + file.name + "…");
      const data = await api(
        "/api/upload?" + new URLSearchParams({ name: file.name }),
        file,
        true,
      );
      const type = file.name.split(".").pop().toLowerCase();
      await loadFiles("imports");
      if (["mp4", "mov", "mkv", "webm", "m4v", "avi"].includes(type))
        selectSource(data.path);
      else if (type === "srt") await loadTranscript(data.path);
    }
    toast("素材导入完成");
  } catch (e) {
    toast(e.message, true);
  } finally {
    uploading = false;
    $("#upload").disabled = false;
    $("#upload-files").value = "";
  }
}
function drawTrack(selector, segments, total, type) {
  const track = $(selector);
  track.replaceChildren();
  segments.forEach((item, i) => {
    const node = el(
      "button",
      "",
      type === "video"
        ? String(i + 1).padStart(2, "0") + " " + time(item.source_start_ms || 0)
        : type === "caption"
          ? item.text
          : "♫ 背景音乐",
    );
    node.style.left = (item.start_ms / total) * 100 + "%";
    node.style.width = (item.duration_ms / total) * 100 + "%";
    node.title =
      type === "caption"
        ? item.text
        : time(item.start_ms) +
          " / " +
          (item.duration_ms / 1000).toFixed(2) +
          " 秒";
    node.onclick = () => {
      switchVideo("output");
      $("#player").currentTime = item.start_ms / 1000;
    };
    track.append(node);
  });
}
function renderDetail(data) {
  detail = data;
  const { status, plan, review, quality } = data;
  $("#job-status").lastElementChild.textContent =
    stageNames[status.stage] || status.stage;
  $("#resume").hidden = !["failed", "interrupted"].includes(status.state);
  if (status.error) toast(status.error, true);
  if (plan) {
    const total = Math.max(
      ...plan.video.map((c) => c.start_ms + c.duration_ms),
      1,
    );
    $("#clip-count").textContent = plan.video.length + " 个片段";
    $("#ruler-mid").textContent = time(total / 2);
    $("#ruler-end").textContent = time(total);
    $("#canvas-label").textContent =
      plan.canvas.width +
      " × " +
      plan.canvas.height +
      " / " +
      plan.canvas.fps +
      " fps";
    drawTrack("#video-track", plan.video, total, "video");
    drawTrack("#caption-track", plan.captions, total, "caption");
    drawTrack("#music-track", plan.audio, total, "music");
  }
  if (review) {
    const rows = review.policy_decisions || [];
    $("#review-count").textContent = rows.filter(
      (r) => r.action === "EXCLUDE",
    ).length;
    $("#review-list").replaceChildren();
    for (const r of rows) {
      const row = el(
        "div",
        "review-row" + (r.action === "KEEP" ? " kept" : ""),
      );
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.dataset.cue = r.cue;
      checkbox.checked = r.applied;
      checkbox.disabled = r.action === "KEEP" || r.blocked_by.length > 0;
      checkbox.setAttribute("aria-label", "删除第 " + r.cue + " 句");
      row.append(checkbox);
      const text = el("div");
      text.append(
        el("div", "", r.cue + ". " + r.text),
        el("div", "reason", r.reason),
      );
      if (r.blocked_by.length)
        text.append(el("div", "blocked", "保护：" + r.blocked_by.join(" · ")));
      row.append(
        text,
        el(
          "span",
          "action",
          r.action === "KEEP" ? "保留" : r.applied ? "已删除" : "建议删除",
        ),
      );
      $("#review-list").append(row);
    }
    if (review.target_met === false)
      $("#quality-info").textContent = "目标时长未达到；受保护内容已保留。";
  }
  if (status.state === "completed") {
    outputUrl = artifact("video");
    $("#view-output").disabled = false;
    $("#export-top").disabled = false;
    $("#downloads").hidden = false;
    $("#downloads").replaceChildren();
    for (const [kind, label] of [
      ["video", "MP4 成片 ↗"],
      ["srt", "字幕 SRT"],
      ["plan", "时间线 JSON"],
      ["review", "删留报告"],
      ["quality", "质量报告"],
      ["jianying", "剪映适配计划"],
    ]) {
      const a = el("a", "", label);
      a.href = artifact(kind);
      a.download = kind === "video" ? "VIDEO-Clips.mp4" : "";
      $("#downloads").append(a);
    }
    if (quality)
      $("#quality-info").textContent =
        "✓ " +
        quality.decoded_frames +
        " 帧 · 音视频解码通过" +
        (review?.target_met === false ? " · 未达目标时长" : "");
  }
  $("#apply-review").hidden =
    $("#review-list").hidden || status.state !== "completed";
}
function hydrate(input) {
  if (!input) return;
  source = input.source;
  originalUrl = mediaUrl(source);
  $("#source-label").textContent = source.split("/").pop();
  cues = input.cues;
  renderCues();
  $("#transcript-label").textContent = cues.length + " 句 · 任务原始转写";
  const o = input.options;
  $("#instruction").value = o.instruction;
  strategy = o.strategy;
  $$("[data-strategy]").forEach((b) =>
    b.classList.toggle("selected", b.dataset.strategy === strategy),
  );
  $("#target").value = o.target_ms ? o.target_ms / 1000 : "";
  $("#protected-terms").value = o.protected_terms.join(", ");
  $("#apply-cuts").checked = o.apply_cuts;
  $("#aspect").value = input.aspect;
  $("#music-volume").value = input.music_volume;
  $("#volume-value").value = Math.round(input.music_volume * 100) + "%";
  if (input.music) {
    const option = el("option", "", input.music.split("/").pop());
    option.value = input.music;
    $("#music-select").append(option);
    $("#music-select").value = input.music;
  } else $("#music-select").value = "";
  if (input.model) {
    $("#provider-mode").value = "model";
    $("#endpoint").value = input.model.endpoint;
    $("#model").value = input.model.model;
  } else {
    $("#provider-mode").value = "offline";
    const option = el("option", "", input.response_file.split("/").pop());
    option.value = input.response_file;
    $("#response-select").append(option);
    $("#response-select").value = input.response_file;
  }
  providerMode();
  switchVideo("source");
}
async function loadJob(id) {
  if (!id) return;
  currentJob = id;
  $("#job-select").value = id;
  detail = null;
  outputUrl = "";
  $("#view-output").disabled = true;
  $("#export-top").disabled = true;
  $("#downloads").hidden = true;
  $("#quality-info").textContent = "";
  const data = await api("/api/job?" + new URLSearchParams({ id }));
  hydrate(data.input);
  renderDetail(data);
}
async function refreshJobs() {
  const jobs = await api("/api/jobs");
  const old = currentJob;
  $("#job-select").replaceChildren(el("option", "", "选择任务"));
  $("#job-select").firstChild.value = "";
  for (const job of jobs) {
    const o = el(
      "option",
      "",
      job.source +
        " · " +
        (stageNames[job.stage] || job.state) +
        " · " +
        job.id.slice(0, 6),
    );
    o.value = job.id;
    $("#job-select").append(o);
  }
  if (old) $("#job-select").value = old;
  return jobs;
}
async function run() {
  if (!source) throw Error("先选择一个视频。");
  if (!cues.length) throw Error("先导入带时间戳的字幕。");
  const offline = $("#provider-mode").value === "offline";
  if (offline && !$("#response-select").value)
    throw Error("请选择已有的 AI 决策 JSON。");
  const payload = {
    source,
    cues,
    instruction: $("#instruction").value,
    strategy,
    target_ms: $("#target").value
      ? Math.round(Number($("#target").value) * 1000)
      : null,
    protected_terms: $("#protected-terms")
      .value.split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
    apply_cuts: $("#apply-cuts").checked,
    aspect: $("#aspect").value,
    music: $("#music-select").value || null,
    music_volume: Number($("#music-volume").value),
    response: offline ? $("#response-select").value : null,
    endpoint: $("#endpoint").value,
    model: $("#model").value,
    allow_paid: !offline && $("#allow-paid").checked,
  };
  $("#run").disabled = true;
  try {
    const job = await api("/api/jobs", payload);
    await refreshJobs();
    await loadJob(job.id);
    toast("任务已加入本地队列");
  } finally {
    $("#run").disabled = false;
  }
}
async function applyReview() {
  const excluded = $$("#review-list input:checked")
    .filter((n) => !n.disabled)
    .map((n) => Number(n.dataset.cue));
  $("#apply-review").disabled = true;
  try {
    const job = await api("/api/review", { id: currentJob, excluded });
    await refreshJobs();
    await loadJob(job.id);
    toast("审核结果已保存为新版本，开始本地渲染；不再调用模型。");
  } finally {
    $("#apply-review").disabled = false;
  }
}
$("#refresh").onclick = () => loadFiles().catch((e) => toast(e.message, true));
$("#upload").onclick = $("#empty-import").onclick = () =>
  $("#upload-files").click();
$("#upload-files").onchange = (e) => uploadFiles(e.target.files);
$("#drop-area").ondragover = (e) => {
  e.preventDefault();
  e.currentTarget.classList.add("dragging");
};
$("#drop-area").ondragleave = (e) =>
  e.currentTarget.classList.remove("dragging");
$("#drop-area").ondrop = (e) => {
  e.preventDefault();
  e.currentTarget.classList.remove("dragging");
  uploadFiles(e.dataTransfer.files);
};
$$("[data-strategy]").forEach(
  (b) =>
    (b.onclick = () => {
      strategy = b.dataset.strategy;
      $$("[data-strategy]").forEach((n) =>
        n.classList.toggle("selected", n === b),
      );
    }),
);
$("#provider-mode").onchange = providerMode;
$("#music-volume").oninput = () =>
  ($("#volume-value").value =
    Math.round(Number($("#music-volume").value) * 100) + "%");
$("#tab-transcript").onclick = () => showTab("transcript");
$("#tab-review").onclick = () => showTab("review");
$("#view-source").onclick = () => switchVideo("source");
$("#view-output").onclick = () => switchVideo("output");
$("#run").onclick = () => run().catch((e) => toast(e.message, true));
$("#apply-review").onclick = () =>
  applyReview().catch((e) => toast(e.message, true));
$("#job-select").onchange = (e) =>
  loadJob(e.target.value).catch((e) => toast(e.message, true));
$("#resume").onclick = async () => {
  try {
    await api("/api/resume", { id: currentJob });
    await loadJob(currentJob);
  } catch (e) {
    toast(e.message, true);
  }
};
$("#export-top").onclick = () => {
  if (outputUrl) {
    const a = el("a");
    a.href = outputUrl;
    a.download = "VIDEO-Clips.mp4";
    a.click();
  }
};
$("#player").ontimeupdate = () =>
  ($("#time-display").textContent =
    time($("#player").currentTime * 1000) +
    " / " +
    time(($("#player").duration || 0) * 1000));
async function init() {
  if (!token) {
    $("#connection").textContent = "需要会话链接";
    throw Error("使用终端输出的完整本地会话链接打开界面。");
  }
  await loadFiles();
  await refreshJobs();
  $("#connection").textContent = "● 已连接";
  $("#status-text").textContent = "就绪 · 真实本地剪辑引擎已连接";
}
init().catch((e) => toast(e.message, true));
setInterval(async () => {
  if (polling || !currentJob) return;
  polling = true;
  try {
    const data = await api(
      "/api/job?" + new URLSearchParams({ id: currentJob }),
    );
    const changed =
      data.status.state !== detail?.status.state ||
      data.status.stage !== detail?.status.stage;
    if (changed) {
      renderDetail(data);
      await refreshJobs();
    }
  } catch (e) {
    $("#connection").textContent = "连接中断";
  } finally {
    polling = false;
  }
}, 1500);
