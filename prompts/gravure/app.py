#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["gradio>=4.0.0,<6"]
# ///
"""Local page that composes gravure prompt text and can send one line to Forge."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields
from copy import deepcopy
import random
import sys
import threading
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forge import DEFAULT_SAMPLER, DEFAULT_URL, _decode_image, progress, progress_note, sampler_names, txt2img
from library import WEAR_LABEL, SLOT_LABEL, POOL_LABEL, PRESENCE_LABEL, SEASON_LABEL, Options, PromptLibrary, generate, reroll_part


def _pack_forge(url, width, height, steps, cfg, distilled, sampler, image_seed, batch):
    count = int(1 if batch is None else batch)
    return {
        "url": url or DEFAULT_URL,
        "width": int(width or 832),
        "height": int(height or 1216),
        "steps": int(8 if steps is None else steps),
        "cfg": float(1 if cfg is None else cfg),
        "distilled": float(1.15 if distilled is None else distilled),
        "sampler": sampler or DEFAULT_SAMPLER,
        "image_seed": int(-1 if image_seed is None else image_seed),
        "batch": max(1, min(8, count)),
    }


def _forge_one(prompt, negative, url, width, height, steps, cfg, distilled, sampler, image_seed, batch):
    packed = _pack_forge(url, width, height, steps, cfg, distilled, sampler, image_seed, batch)
    if not (prompt or "").strip():
        yield gr.skip(), "英語の1行が空です。", packed
        return
    box: dict = {}

    def run() -> None:
        try:
            box["result"] = txt2img(
                prompt,
                negative,
                url=url,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                distilled=distilled,
                sampler=sampler,
                seed=image_seed,
                batch=batch,
            )
        except Exception as exc:
            box["result"] = ([], f"生成に失敗しました。{exc}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield gr.skip(), "生成しています…", gr.skip()
    seen_step = None
    seen_note = "生成しています…"
    while thread.is_alive():
        body = progress(url)
        preview = None
        state = (body or {}).get("state") if isinstance(body, dict) else None
        step_key = None
        if isinstance(state, dict) and state.get("job_count"):
            step_key = (state.get("job_no"), state.get("sampling_step"))
        current = (body or {}).get("current_image") if isinstance(body, dict) else None
        if current and step_key != seen_step:
            seen_step = step_key
            preview = [_decode_image(str(current))]
        note = progress_note(body)
        if preview or note != seen_note:
            seen_note = note
            yield (preview if preview else gr.skip()), note, gr.skip()
        thread.join(0.4)
    images, message = box.get("result") or ([], "生成に失敗しました。")
    if images:
        yield images, message, packed
    else:
        yield gr.skip(), message, packed


def _restore_forge(payload):
    if not isinstance(payload, dict) or "url" not in payload:
        return (gr.skip(),) * 9
    packed = _pack_forge(
        payload.get("url"),
        payload.get("width"),
        payload.get("height"),
        payload.get("steps"),
        payload.get("cfg"),
        payload.get("distilled"),
        payload.get("sampler"),
        payload.get("image_seed"),
        payload.get("batch"),
    )
    return (
        packed["url"],
        packed["width"],
        packed["height"],
        packed["steps"],
        packed["cfg"],
        packed["distilled"],
        packed["sampler"],
        packed["image_seed"],
        packed["batch"],
    )

POOL_CHOICES = [
    ("グラビア · ホーズ", "hosiery"),
    ("グラビア · テーラード", "tailored"),
    ("グラビア · ニット", "knit"),
    ("グラビア · ドレス", "dress"),
    ("グラビア · イブニング", "evening"),
    ("グラビア · 水着", "swim"),
    ("日常 · カジュアル", "casual"),
    ("日常 · きれいめ", "neat"),
    ("コスチューム · メイド", "maid"),
    ("コスチューム · 和装", "wa"),
    ("コスチューム · ステージ", "stage"),
    ("コスチューム · クラシカル", "classic"),
    ("子供っぽい · ガーリー", "girly"),
    ("子供っぽい · モチーフ", "motif"),
]
SEASON_CHOICES = [(label, key) for key, label in SEASON_LABEL.items()]
PRESENCE_CHOICES = [(label, key) for key, label in PRESENCE_LABEL.items()]
DEFAULT_PRESENCES = ["none", "few", "many"]
DEFAULT_POOLS = ["hosiery", "tailored", "knit", "dress", "evening"]
LEGACY_POOLS = {
    "gravure": ("hosiery", "tailored", "knit", "dress", "evening"),
    "daily": ("casual", "neat"),
    "costume": ("maid", "wa", "stage", "classic"),
    "childish": ("girly", "motif"),
}
CSS = """
.gradio-container,
.gradio-container textarea,
.gradio-container input,
.gradio-container label,
.gradio-container button {
  font-family: "Segoe UI", "Yu Gothic UI", Meiryo, sans-serif !important;
}
html,
body,
.gradio-container,
.gradio-container .wrap,
.gradio-container .contain {
  max-width: 100% !important;
  overflow-x: hidden !important;
}
.gradio-container {
  font-size: 16px;
}
.gradio-container footer {
  display: none !important;
}
.gradio-container textarea {
  font-size: 17px !important;
  line-height: 1.75 !important;
  white-space: pre-wrap !important;
  overflow-wrap: anywhere !important;
  overflow-x: hidden !important;
}
.toolbar {
  align-items: flex-end !important;
  flex-wrap: wrap !important;
  gap: 8px;
  margin: 8px 0 4px;
  max-width: 100%;
  min-width: 0 !important;
}
.workspace {
  align-items: stretch !important;
  flex-wrap: nowrap !important;
  max-width: 100%;
  min-width: 0 !important;
  overflow-x: hidden !important;
}
.pane {
  flex-wrap: nowrap !important;
  min-width: 0 !important;
  max-width: 100%;
  max-height: calc(100vh - 108px);
  overflow-x: hidden !important;
  overflow-y: auto;
  padding-right: 8px;
  scrollbar-color: #374151 #e5e7eb;
  scrollbar-width: auto;
}
.pane .form,
.pane .block,
.pane fieldset {
  flex-wrap: nowrap !important;
  flex-shrink: 0 !important;
  height: auto !important;
  max-width: 100% !important;
  min-width: 0 !important;
  overflow-x: hidden !important;
}
.pane label {
  white-space: normal !important;
  overflow-wrap: anywhere;
}
.pane::-webkit-scrollbar {
  width: 16px;
}
.pane::-webkit-scrollbar-track {
  background: #e5e7eb;
  border-radius: 8px;
}
.pane::-webkit-scrollbar-thumb {
  background: #374151;
  border: 3px solid #e5e7eb;
  border-radius: 8px;
}
.prompt-card {
  margin: 0 0 12px;
  padding: 8px 12px 4px;
  border: 1px solid var(--border-color-primary);
  border-radius: 12px;
}
.prompt-card .preview-slot:not(:has(img)) {
  display: none !important;
}
.prompt-card .preview-slot img {
  max-height: 720px;
  object-fit: contain !important;
}
.prompt-text textarea {
  font-family: "Segoe UI", "Yu Gothic UI", Meiryo, sans-serif !important;
  font-size: 17px !important;
  line-height: 1.75 !important;
}
.prompt-card .note-scroll textarea {
  height: calc(1.75em * 14 + 12px) !important;
  max-height: 60vh !important;
  min-height: calc(1.75em * 10 + 12px) !important;
  overflow-y: auto !important;
  scrollbar-gutter: stable;
  scrollbar-width: auto;
  scrollbar-color: #374151 #e5e7eb;
  resize: vertical !important;
}
.prompt-card .note-scroll textarea::-webkit-scrollbar { width: 14px; }
.prompt-card .note-scroll textarea::-webkit-scrollbar-track { background: #e5e7eb; }
.prompt-card .note-scroll textarea::-webkit-scrollbar-thumb {
  background: #374151;
  border: 3px solid #e5e7eb;
  border-radius: 8px;
}
.prompt-card .english-one { --prompt-lines: 6; }
.prompt-card .english-parts { --prompt-lines: 12; }
.prompt-card .english-scroll textarea {
  height: calc(1.75em * var(--prompt-lines) + 12px) !important;
  max-height: 50vh !important;
  min-height: 6rem !important;
  overflow-y: auto !important;
  scrollbar-gutter: stable;
  scrollbar-width: auto;
  scrollbar-color: #374151 #e5e7eb;
  resize: vertical !important;
}
.prompt-card .english-scroll textarea::-webkit-scrollbar { width: 14px; }
.prompt-card .english-scroll textarea::-webkit-scrollbar-track { background: #e5e7eb; }
.prompt-card .english-scroll textarea::-webkit-scrollbar-thumb {
  background: #374151;
  border: 3px solid #e5e7eb;
  border-radius: 8px;
}
button.copied {
  outline: 2px solid #166534;
}
"""
COPY_HEAD = """
<script>
document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const name = (button.innerText || "").replace(/\\s+/g, "");
  const label = {
    "解説をコピー": "解説",
    "1行をコピー": "1行",
    "パートをコピー": "パート",
    "ネガティブをコピー": "ネガティブ",
  }[name];
  if (!label) return;
  const text = findCopyText(button, label);
  if (text == null) return;
  copyNow(text);
  const span = button.querySelector("span") || button;
  const previous = span.textContent;
  span.textContent = "コピーしました";
  button.classList.add("copied");
  setTimeout(() => {
    span.textContent = previous;
    button.classList.remove("copied");
  }, 900);
}, true);

function labeledValue(root, label) {
  for (const lab of root.querySelectorAll("label")) {
    const span = lab.querySelector("span");
    const text = (span ? span.textContent : lab.textContent).trim();
    if (text !== label) continue;
    const block = lab.closest(".block");
    const area = block && block.querySelector("textarea");
    if (area) return area.value;
  }
  return null;
}

function findCopyText(button, label) {
  let node = button.parentElement;
  while (node && node !== document.body) {
    const labeled = labeledValue(node, label);
    if (labeled != null) return labeled;
    if (label === "ネガティブ" && node.querySelectorAll("textarea").length === 1) {
      return node.querySelector("textarea").value;
    }
    node = node.parentElement;
  }
  return null;
}

function copyNow(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.left = "0";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus();
  area.select();
  try {
    document.execCommand("copy");
  } catch (error) {}
  document.body.removeChild(area);
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
  }
}
</script>
"""
STORAGE_KEY = "gravure-prompt-v1"
STORAGE_SECRET = "gravure-prompt-local"


def _choices(lib: PromptLibrary, slot: str) -> list[tuple[str, str]]:
    return [(f"{block.block_id} — {block.title}", block.key) for block in lib.by_slot(slot)]


def _choice_values(choices: list) -> list[str]:
    values: list[str] = []
    for item in choices:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            values.append(str(item[1]))
        else:
            values.append(str(item))
    return [value for value in values if value and value != "__empty__"]


def _unique_label(label: str, used: set[str]) -> str:
    if label not in used:
        used.add(label)
        return label
    number = 2
    while f"{label}{number}" in used:
        number += 1
    unique = f"{label}{number}"
    used.add(unique)
    return unique


_FILE_GROUP = {
    "ポーズ.md": "基本",
    "立ち姿.md": "立ち姿",
    "バリエーション追加.md": "追加",
    "表情.md": "基本",
    "グラビア表情.md": "グラビア",
}
_GROUP_ORDER = {"基本": 0, "立ち姿": 1, "追加": 2}


def _selection_groups(lib: PromptLibrary, slot: str) -> list[tuple[str, tuple[str, ...]]]:
    files: dict[str, list] = {}
    for block in lib.blocks.values():
        if block.slot != slot:
            continue
        files.setdefault(Path(block.source).name, []).append(block)
    used: set[str] = set()
    groups: list[tuple[str, tuple[str, ...]]] = []
    for filename, blocks in files.items():
        sections: list[tuple[str, list[str]]] = []
        for block in blocks:
            if not sections or sections[-1][0] != block.section:
                sections.append((block.section, []))
            sections[-1][1].append(block.key)
        collapse = (len(sections) >= 3 and all(len(keys) == 1 for _, keys in sections)) or all(not name for name, _ in sections)
        if collapse or (len(sections) == 1 and not sections[0][0]):
            raw = _FILE_GROUP.get(filename) or Path(filename).stem
            groups.append((_unique_label(raw, used), tuple(block.key for block in blocks)))
            continue
        for name, keys in sections:
            raw = name or _FILE_GROUP.get(filename) or Path(filename).stem
            groups.append((_unique_label(raw, used), tuple(keys)))
    groups.sort(key=lambda item: _GROUP_ORDER.get(item[0], 50))
    return groups


def _ordered(selected: list[str] | None, ordered: list[str]) -> list[str]:
    chosen = set(selected or [])
    return [key for key in ordered if key in chosen]


def _with_bulk(
    choices: list,
    value: list[str],
    groups: list[tuple[str, tuple[str, ...]]] | None = None,
    *,
    label: str | None = None,
    info: str | None = None,
    show_label: bool = True,
    visible: bool = True,
    interactive: bool = True,
) -> gr.CheckboxGroup:
    ordered = _choice_values(choices)
    with gr.Row(visible=visible):
        select_all = gr.Button("全選択", size="sm", scale=1)
        select_none = gr.Button("全解除", size="sm", scale=1)
    sections = None
    prev = None
    initial_sections: list[str] = []
    key_map: dict[str, tuple[str, ...]] = {}
    if groups and len(groups) >= 2:
        names = [name for name, _ in groups]
        key_map = dict(groups)
        initial_sections = [name for name, keys in groups if set(keys) <= set(value)]
        sections = gr.CheckboxGroup(
            label="セクション",
            choices=names,
            value=initial_sections,
            info="オンでその候補をまとめ選び、オフで外します。",
            visible=visible,
        )
        prev = gr.State(list(initial_sections))
    box = gr.CheckboxGroup(
        label=label,
        show_label=show_label and bool(label),
        choices=choices,
        value=value,
        info=info,
        visible=visible,
        interactive=interactive,
    )
    if sections is None:
        select_all.click(lambda: list(ordered), outputs=box)
        select_none.click(lambda: [], outputs=box)
        return box

    def on_sections(selected, previous, current):
        selected_set = set(selected or [])
        previous_set = set(previous or [])
        current_set = set(current or [])
        for name in selected_set - previous_set:
            current_set.update(key_map.get(name, ()))
        for name in previous_set - selected_set:
            current_set.difference_update(key_map.get(name, ()))
        updated = _ordered(list(current_set), ordered)
        if updated == _ordered(current, ordered):
            return gr.skip(), list(selected or [])
        return updated, list(selected or [])

    def on_items(current):
        current_set = set(current or [])
        active = [name for name, keys in groups if keys and set(keys) <= current_set]
        return active, active

    sections.change(on_sections, inputs=[sections, prev, box], outputs=[box, prev])
    box.change(on_items, inputs=[box], outputs=[sections, prev])
    select_all.click(lambda: (list(ordered), list(names), list(names)), outputs=[box, sections, prev])
    select_none.click(lambda: ([], [], []), outputs=[box, sections, prev])
    return box


def _clean(values: list[str] | None, valid: set[str]) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(value for value in values if value in valid)


def _expand_pools(saved: object) -> list[str]:
    expanded: list[str] = []
    for value in _as_list(saved):
        expanded.extend(LEGACY_POOLS.get(value, (value,)))
    return list(_clean(expanded, set(POOL_LABEL)))


def _int(value: float | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _roll_seed() -> int:
    return random.SystemRandom().randint(1, 2_147_483_647)


def _as_list(value: object) -> list[str]:
    if not value or not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item]


def _merge_new(saved: object, known: object, ordered: list[str], *, include_new: bool) -> list[str]:
    valid = set(ordered)
    selected = [key for key in _as_list(saved) if key in valid]
    if not include_new:
        return selected
    seen = set(_as_list(known)) if isinstance(known, (list, tuple)) else set(selected)
    have = set(selected)
    for key in ordered:
        if key not in seen and key not in have:
            selected.append(key)
    return selected


def _pack_session(
    count,
    seed,
    randomize,
    person,
    cameras,
    shots,
    lights,
    poses,
    expressions,
    outfit_pools,
    hair_pools,
    acc_pools,
    seasons,
    prop_mode,
    prop_max,
    backgrounds,
    presences,
    lock_camera,
    lock_shot,
    lock_pose,
    lock_expression,
    lock_hair,
    lock_acc,
    lock_outfit,
    lock_prop,
    lock_bg,
    lock_light,
    finish_key,
    finish_strength,
    wear_hair_accessory,
    wear_earrings,
    wear_neckwear,
    wear_wristwear,
    wear_handwear,
    wear_legwear,
    wear_footwear,
    wear_extra_accessory,
    wear_halo,
    wear_backwear,
    wear_tail,
    costume_key,
    notes,
    negative,
    items,
) -> dict:
    return {
        "count": _int(count, 4),
        "seed": _int(seed, 1),
        "randomize": bool(randomize),
        "person": person or "",
        "cameras": _as_list(cameras),
        "shots": _as_list(shots),
        "lights": _as_list(lights),
        "poses": _as_list(poses),
        "expressions": _as_list(expressions),
        "outfit_pools": _as_list(outfit_pools),
        "hair_pools": _as_list(hair_pools),
        "acc_pools": _as_list(acc_pools),
        "seasons": list(_clean(_as_list(seasons), set(SEASON_LABEL))),
        "prop_mode": prop_mode if prop_mode in {"off", "pop"} else "off",
        "prop_max": max(1, min(3, _int(prop_max, 1))),
        "backgrounds": _as_list(backgrounds),
        "presences": list(_clean(_as_list(presences), set(PRESENCE_LABEL))),
        "lock_camera": lock_camera or "",
        "lock_shot": lock_shot or "",
        "lock_pose": lock_pose or "",
        "lock_expression": lock_expression or "",
        "lock_hair": lock_hair or "",
        "lock_acc": lock_acc or "",
        "lock_outfit": lock_outfit or "",
        "lock_prop": lock_prop or "",
        "lock_bg": lock_bg or "",
        "lock_light": lock_light or "",
        "wear_parts": dict(zip(WEAR_LABEL, [wear_hair_accessory, wear_earrings, wear_neckwear, wear_wristwear, wear_handwear, wear_legwear, wear_footwear, wear_extra_accessory, wear_halo, wear_backwear, wear_tail])),
        "costume_key": costume_key or "",
        "wardrobe_version": 2,
        "finish_key": finish_key or "",
        "finish_strength": finish_strength if finish_strength in {"weak", "standard", "strong"} else "standard",
        "notes": notes or "",
        "negative": negative or "",
        "items": items if isinstance(items, list) else [],
    }


def _library_counts(lib: PromptLibrary) -> str:
    """Count loaded blocks, independently of generation selections."""
    def table(headers, rows):
        def cell(value):
            return str(value).replace("|", "\\|").replace("\n", " ")
        return "\n".join([
            "| " + " | ".join(map(cell, headers)) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(map(cell, row)) + " |" for row in rows),
        ])

    blocks = list(lib.blocks.values())
    sections = [
        f"## 登録プロンプト：{len(blocks)}件",
        "起動時に読み込んだ候補の件数です。生成画面の選択状態には左右されません。Markdownを追加・変更したら、アプリを起動し直してください。",
        "### パーツ別",
        table(["パーツ", "件数"], [
            [label, len(lib.by_slot(slot))] for slot, label in SLOT_LABEL.items()
        ]),
        "### 衣装・髪型・部位別の系統別",
        table(["系統", "衣装", "髪型", *WEAR_LABEL.values()], [
            [label, *(sum(pool in b.pools for b in lib.by_slot(slot))
                       for slot in ("outfit", "hair", *WEAR_LABEL))]
            for pool, label in POOL_LABEL.items() if pool != "pop"
        ]),
        "複数の系統に属する候補は、それぞれに数えています。系統別の合計は登録総数とは一致しません。",
        "### 背景の場所・人の入り別",
        table(["場所", "無人", "人が少ない", "人が多い", "計"], [
            [category, *(sum(p in (b.presences or ("none",)) for b in lib.by_slot("background")
                            if b.category == category) for p in PRESENCE_LABEL),
             sum(b.category == category for b in lib.by_slot("background"))]
            for category in lib.categories("background")
        ]),
        "### 季節別",
        table(["パーツ", "通年", *SEASON_LABEL.values()], [
            [label, sum(not b.seasons for b in lib.by_slot(slot)),
             *(sum(season in b.seasons for b in lib.by_slot(slot)) for season in SEASON_LABEL)]
            for slot, label in SLOT_LABEL.items() if lib.by_slot(slot)
        ]),
        "季節別は登録タグの件数です。複数の季節に属する候補は各季節に数え、生成時の通年候補との組み合わせは含めません。人の入りが複数指定された背景も、各区分に数えています。",
        "### コスチュームのプリセット",
        table(["系統", "件数"], [[category, sum(b.category == category for b in lib.by_slot("costume"))]
                                 for category in lib.categories("costume")]),
        "### 小道具の系統別",
        table(["系統", "件数"], [["小道具", sum("pop" in b.pools for b in lib.by_slot("prop"))]]),
    ]
    return "\n\n".join(sections)


def _build(lib: PromptLibrary):
    camera_choices = _choices(lib, "camera")
    shot_choices = _choices(lib, "shot")
    light_choices = _choices(lib, "lighting")
    pose_choices = _choices(lib, "pose")
    expression_choices = _choices(lib, "expression")
    hair_blocks = lib.by_slot("hair")
    acc_blocks = lib.by_slot("accessory")
    outfit_blocks = lib.by_slot("outfit")
    prop_blocks = lib.by_slot("prop")
    bg_blocks = lib.by_slot("background")
    bg_categories = lib.categories("background")

    camera_keys = {key for _, key in camera_choices}
    shot_keys = {key for _, key in shot_choices}
    light_keys = {key for _, key in light_choices}
    pose_keys = {key for _, key in pose_choices}
    expression_keys = {key for _, key in expression_choices}
    bg_keys = set(bg_categories)

    def lock_choices(blocks: list) -> list[tuple[str, str]]:
        return [("ランダム", "")] + [(f"{block.block_id} — {block.title}", block.key) for block in blocks]

    def on_generate(
        count,
        seed,
        randomize,
        person,
        cameras,
        shots,
        lights,
        poses,
        expressions,
        outfit_pools,
        hair_pools,
        acc_pools,
        seasons,
        prop_mode,
        prop_max,
        backgrounds,
        presences,
        lock_camera,
        lock_shot,
        lock_pose,
        lock_expression,
        lock_hair,
        lock_acc,
        lock_outfit,
        lock_prop,
        lock_bg,
        lock_light,
        finish_key,
        finish_strength,
        wear_hair_accessory,
        wear_earrings,
        wear_neckwear,
        wear_wristwear,
        wear_handwear,
        wear_legwear,
        wear_footwear,
        wear_extra_accessory,
        wear_halo,
        wear_backwear,
        wear_tail,
        costume_key,
    ):
        used_seed = _roll_seed() if randomize else _int(seed, 1)
        options = Options(
            count=_int(count, 4),
            seed=used_seed,
            person=person or "",
            camera_keys=_clean(cameras, camera_keys),
            shot_keys=_clean(shots, shot_keys),
            pose_keys=_clean(poses, pose_keys),
            expression_keys=_clean(expressions, expression_keys),
            light_keys=_clean(lights, light_keys),
            outfit_pools=_clean(outfit_pools, set(POOL_LABEL)),
            costume_key=costume_key or "",
            hair_pools=_clean(hair_pools, set(POOL_LABEL)),
            accessory_pools=(),
            seasons=_clean(seasons, set(SEASON_LABEL)),
            presences=_clean(presences, set(PRESENCE_LABEL)),
            prop_mode=prop_mode if prop_mode in {"off", "pop"} else "off",
            prop_max=max(1, _int(prop_max, 1)),
            background_categories=_clean(backgrounds, bg_keys),
            finish_key=finish_key or "",
            finish_strength=finish_strength,
            wear_parts=dict(zip(WEAR_LABEL, [wear_hair_accessory, wear_earrings, wear_neckwear, wear_wristwear, wear_handwear, wear_legwear, wear_footwear, wear_extra_accessory, wear_halo, wear_backwear, wear_tail])),
            locks={
                "camera": lock_camera or "",
                "shot": lock_shot or "",
                "pose": lock_pose or "",
                "expression": lock_expression or "",
                "hair": lock_hair or "",
                "accessory": "",
                "outfit": lock_outfit or "",
                "prop": lock_prop or "",
                "background": lock_bg or "",
                "lighting": lock_light or "",
            },
        )
        result = generate(lib, options)
        items = [{"parts": parts, "one": one, "ja": note,
                  "rows": rows, "options": asdict(options)}
                 for (parts, one, note), rows in zip(result.items, result.row_items)]
        session = _pack_session(
            count,
            used_seed,
            randomize,
            person,
            cameras,
            shots,
            lights,
            poses,
            expressions,
            outfit_pools,
            hair_pools,
            acc_pools,
            seasons,
            prop_mode,
            prop_max,
            backgrounds,
            presences,
            lock_camera,
            lock_shot,
            lock_pose,
            lock_expression,
            lock_hair,
            lock_acc,
            lock_outfit,
            lock_prop,
            lock_bg,
            lock_light,
            finish_key,
            finish_strength,
            wear_hair_accessory,
            wear_earrings,
            wear_neckwear,
            wear_wristwear,
            wear_handwear,
            wear_legwear,
            wear_footwear,
            wear_extra_accessory,
            wear_halo,
            wear_backwear,
            wear_tail,
            costume_key,
            result.notes,
            result.negative,
            items,
        )
        session["known"] = {
            "cameras": [key for _, key in camera_choices],
            "shots": [key for _, key in shot_choices],
            "lights": [key for _, key in light_choices],
            "poses": [key for _, key in pose_choices],
            "expressions": [key for _, key in expression_choices],
            "backgrounds": list(bg_categories),
        }
        return result.notes, result.negative, items, session, used_seed

    def on_reroll(target, card, current_one, current_parts, current_note, session, card_index):
        skips = (gr.skip(),) * 5
        if not isinstance(card, dict) or not card.get("rows") or not isinstance(card.get("options"), dict):
            return (*skips, "このカードは旧形式です。「プロンプトを作る」で作り直してください。")
        if (current_one, current_parts, current_note) != (card.get("one"), card.get("parts"), card.get("ja")):
            return (*skips, "カードに手編集があります。部分変更では上書きしません。編集内容をコピーしてから、プロンプトを作り直してください。")
        try:
            valid = {f.name for f in fields(Options)}
            options = Options(**{key: value for key,value in card["options"].items() if key in valid})
            changed_rows, (parts, one, note) = reroll_part(lib, card["rows"], options, target, _roll_seed())
        except (ValueError, TypeError, KeyError) as exc:
            return (*skips, str(exc))
        updated = deepcopy(card)
        updated.update(rows=changed_rows, parts=parts, one=one, ja=note)
        saved_session = deepcopy(session) if isinstance(session, dict) else {}
        saved_items = list(saved_session.get("items") or [])
        if len(saved_items) < int(card_index):
            return (*skips, "保存されたカードが見つかりません。プロンプトを作り直してください。")
        saved_items[int(card_index)-1] = updated
        saved_session["items"] = saved_items
        label = SLOT_LABEL.get(target, target)
        return one, parts, note, updated, saved_session, f"{label}だけ変更しました。画像へ反映するには、このカードの「生成」を押してください。"

    initial = on_generate(
        4,
        1,
        False,
        "",
        [key for _, key in camera_choices],
        [],
        [key for _, key in light_choices],
        [key for _, key in pose_choices],
        [key for _, key in expression_choices],
        DEFAULT_POOLS,
        DEFAULT_POOLS,
        [],
        [],
        "off",
        1,
        bg_categories,
        DEFAULT_PRESENCES,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "standard",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "inherit",
        "",
    )
    with gr.Blocks(title="グラビア プロンプト", theme=gr.themes.Soft(), css=CSS, head=COPY_HEAD) as demo:
        with gr.Tab("プロンプト作成"):
            with gr.Row(elem_classes=["toolbar"]):
                count = gr.Slider(1, 20, value=4, step=1, label="枚数", scale=2)
                seed = gr.Number(value=1, precision=0, label="seed", scale=1)
                randomize = gr.Checkbox(value=False, label="ランダム")
                person = gr.Textbox(label="人物", lines=1, placeholder="空なら出しません", scale=4)
                go = gr.Button("プロンプトを作る", variant="primary", scale=2)
            saved = gr.BrowserState(None, storage_key=STORAGE_KEY, secret=STORAGE_SECRET)
            forge_saved = gr.BrowserState(None, storage_key="gravure-forge-v1", secret=STORAGE_SECRET)
            with gr.Row(elem_classes=["workspace"]):
                with gr.Column(scale=4, elem_classes=["pane", "options"]):
                    with gr.Accordion("Forge", open=True):
                        gr.Markdown("各カードの1行を、いま Forge に入っているモデルへ送ります。")
                        forge_url = gr.Textbox(label="API", value=DEFAULT_URL)
                        with gr.Row():
                            forge_width = gr.Slider(512, 1536, value=832, step=64, label="幅")
                            forge_height = gr.Slider(512, 1536, value=1216, step=64, label="高さ")
                        with gr.Row():
                            forge_steps = gr.Slider(1, 50, value=8, step=1, label="steps")
                            forge_cfg = gr.Slider(1, 12, value=1, step=0.5, label="CFG")
                            forge_distilled = gr.Slider(0, 12, value=1.15, step=0.05, label="Distilled CFG")
                        samplers = sampler_names()
                        with gr.Row():
                            forge_sampler = gr.Dropdown(
                                label="sampler",
                                choices=samplers,
                                value=DEFAULT_SAMPLER if DEFAULT_SAMPLER in samplers else samplers[0],
                            )
                            forge_batch = gr.Slider(1, 8, value=1, step=1, label="batch count")
                            forge_seed = gr.Number(value=-1, precision=0, label="画像seed")
                    with gr.Accordion("カメラ", open=True):
                        cameras = _with_bulk(
                            camera_choices,
                            [key for _, key in camera_choices],
                            _selection_groups(lib, "camera"),
                            show_label=False,
                        )
                    with gr.Accordion("ポーズ", open=True):
                        poses = _with_bulk(
                            pose_choices or [("（まだありません）", "__empty__")],
                            [key for _, key in pose_choices],
                            _selection_groups(lib, "pose"),
                            show_label=False,
                            visible=bool(pose_choices),
                        )
                    with gr.Accordion("表情", open=True):
                        expressions = _with_bulk(
                            expression_choices or [("（まだありません）", "__empty__")],
                            [key for _, key in expression_choices],
                            _selection_groups(lib, "expression"),
                            show_label=False,
                            visible=bool(expression_choices),
                        )
                    with gr.Accordion("季節", open=True):
                        seasons = _with_bulk(
                            SEASON_CHOICES,
                            [],
                            label=None,
                            show_label=False,
                            info="未選択は通年だけです。選ぶと、その季節の背景と光だけになり、衣装とヘアには通年にその季節が足されます。",
                        )
                    with gr.Accordion("コスチューム・プリセット", open=True):
                        costume_key = gr.Dropdown(
                            label="コスチューム",
                            choices=[("使わない", ""), ("全プリセットからランダム", "random")] +
                                    [(f"{b.category} · {b.title}", b.key) for b in sorted(lib.by_slot("costume"), key=lambda b: (b.category, b.title))],
                            value="",
                        )
                        gr.Markdown("選ぶと衣装本体と部位パーツが一式入ります。部位の「なし」「ランダム」「個別指定」はそちらを優先します。衣装の系統・固定指定よりプリセットを優先し、髪型・ポーズ・背景はそのままです。")
                    with gr.Accordion("衣装・髪型", open=True):
                        outfit_pools = _with_bulk(POOL_CHOICES, list(DEFAULT_POOLS), label="衣装")
                        hair_pools = _with_bulk(POOL_CHOICES, list(DEFAULT_POOLS), label="髪型")
                        acc_pools = gr.CheckboxGroup(label="旧アクセサリ設定", choices=POOL_CHOICES, value=[], visible=False)
                    with gr.Accordion("部位別コーディネート", open=True):
                        gr.Markdown("おまかせは衣装・髪型の元の組み合わせです。元の指定がなければ追加しません。「なし」はその部位を外し、靴の場合は裸足にします。個別指定は季節・系統によらず優先します。")
                        wear_hair_accessory = gr.Dropdown(label=WEAR_LABEL["hair_accessory"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "hair_accessory"), value="inherit")
                        wear_earrings = gr.Dropdown(label=WEAR_LABEL["earrings"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "earrings"), value="inherit")
                        wear_neckwear = gr.Dropdown(label=WEAR_LABEL["neckwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "neckwear"), value="inherit")
                        wear_wristwear = gr.Dropdown(label=WEAR_LABEL["wristwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "wristwear"), value="inherit")
                        wear_handwear = gr.Dropdown(label=WEAR_LABEL["handwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "handwear"), value="inherit")
                        wear_legwear = gr.Dropdown(label=WEAR_LABEL["legwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "legwear"), value="inherit")
                        wear_footwear = gr.Dropdown(label=WEAR_LABEL["footwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "footwear"), value="inherit")
                        wear_extra_accessory = gr.Dropdown(label=WEAR_LABEL["extra_accessory"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "extra_accessory"), value="inherit")
                        wear_halo = gr.Dropdown(label=WEAR_LABEL["halo"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "halo"), value="inherit")
                        wear_backwear = gr.Dropdown(label=WEAR_LABEL["backwear"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "backwear"), value="inherit")
                        wear_tail = gr.Dropdown(label=WEAR_LABEL["tail"], choices=[("コーデにおまかせ", "inherit"), ("なし", "none"), ("ランダム", "random")] + _choices(lib, "tail"), value="inherit")
                    with gr.Accordion("背景と光", open=True):
                        backgrounds = _with_bulk(
                            bg_categories or ["（ファイルなし）"],
                            list(bg_categories),
                            label="背景",
                            interactive=bool(bg_categories),
                        )
                        presences = _with_bulk(PRESENCE_CHOICES, list(DEFAULT_PRESENCES), label="人")
                        lights = _with_bulk(
                            light_choices,
                            [key for _, key in light_choices],
                            _selection_groups(lib, "lighting"),
                            label="ライティング",
                        )
                    with gr.Accordion("構図・小道具", open=False):
                        shots = _with_bulk(
                            shot_choices,
                            [],
                            _selection_groups(lib, "shot"),
                            label="構図",
                        )
                        with gr.Row():
                            prop_mode = gr.Radio(
                                label="小道具",
                                choices=[("オフ", "off"), ("使う", "pop")],
                                value="off",
                            )
                            prop_max = gr.Slider(1, 3, value=1, step=1, label="最大数")
                    with gr.Accordion("撮影質感", open=True):
                        finish_key = gr.Dropdown(label="撮影質感", choices=[("なし", "")] + _choices(lib, "finish"), value="")
                        finish_strength = gr.Radio(label="質感の強さ", choices=[("弱め", "weak"), ("標準", "standard"), ("強め", "strong")], value="standard")
                        gr.Markdown("撮影質感を選ぶと、カメラの角度を残してレンズ・描写・色調を切り替えます。「なし」は元のカメラ指定です。直射フラッシュの質感は、ライティング指定も置き換えます。変更後は「プロンプトを作る」でカードを更新してください。")
                    with gr.Accordion("固定", open=False):
                        lock_camera = gr.Dropdown(label="カメラ", choices=lock_choices(lib.by_slot("camera")), value="", visible=bool(camera_choices))
                        lock_shot = gr.Dropdown(label="構図", choices=lock_choices(lib.by_slot("shot")), value="")
                        lock_light = gr.Dropdown(label="ライティング", choices=lock_choices(lib.by_slot("lighting")), value="")
                        lock_pose = gr.Dropdown(label="ポーズ", choices=lock_choices(lib.by_slot("pose")), value="", visible=bool(pose_choices))
                        lock_expression = gr.Dropdown(
                            label="表情",
                            choices=lock_choices(lib.by_slot("expression")),
                            value="",
                            visible=bool(expression_choices),
                        )
                        lock_outfit = gr.Dropdown(label="衣装", choices=lock_choices(outfit_blocks), value="", visible=bool(outfit_blocks))
                        lock_hair = gr.Dropdown(label="ヘア", choices=lock_choices(hair_blocks), value="", visible=bool(hair_blocks))
                        lock_acc = gr.Dropdown(label="旧アクセサリ固定", choices=lock_choices(acc_blocks), value="", visible=False)
                        lock_prop = gr.Dropdown(label="小道具", choices=lock_choices(prop_blocks), value="", visible=bool(prop_blocks))
                        lock_bg = gr.Dropdown(label="背景", choices=lock_choices(bg_blocks), value="", visible=bool(bg_blocks))
                with gr.Column(scale=7, elem_classes=["pane", "results"]):
                    notes = gr.Markdown(initial[0])
                    prompt_state = gr.State(initial[2])
                    negative = gr.Textbox(
                        show_label=False,
                        lines=3,
                        value=initial[1],
                        interactive=True,
                        elem_classes=["prompt-text"],
                        render=False,
                    )

                    @gr.render(inputs=prompt_state)
                    def render_prompts(items):
                        for index, item in enumerate(items or [], start=1):
                            with gr.Group(elem_classes=["prompt-card"]):
                                gr.Markdown(f"### {index}")
                                note = gr.Textbox(
                                    label="解説",
                                    value=item.get("ja") or "",
                                    lines=14,
                                    max_lines=14,
                                    interactive=True,
                                    elem_classes=["prompt-text", "note-scroll"],
                                )
                                with gr.Accordion("英語", open=False):
                                    one = gr.Textbox(
                                        label="1行",
                                        value=item["one"],
                                        lines=6,
                                        max_lines=6,
                                        interactive=True,
                                        elem_classes=["prompt-text", "english-scroll", "english-one"],
                                    )
                                    parts = gr.Textbox(
                                        label="パート",
                                        value=item["parts"],
                                        lines=12,
                                        max_lines=12,
                                        interactive=True,
                                        elem_classes=["prompt-text", "english-scroll", "english-parts"],
                                    )
                                card_state = gr.State(item)
                                card_index = gr.State(index)
                                with gr.Accordion("このカードの一部を変更", open=False):
                                    reroll_target = gr.Dropdown(
                                        label="変更するパート",
                                        choices=[(SLOT_LABEL[slot], slot) for slot in
                                                 ("pose", "expression", "outfit", "hair", *WEAR_LABEL,
                                                  "background", "lighting", "camera", "shot", "prop")],
                                        value="pose",
                                    )
                                    gr.Markdown("作成時の系統・季節・候補条件で、選んだパートだけ引き直します。対象パートの固定・個別指定は外して抽選します。衣装変更でも靴や装飾は保ちます。")
                                    reroll_button = gr.Button("その部分だけ引き直す", size="sm")
                                    reroll_status = gr.Markdown()
                                reroll_button.click(
                                    on_reroll,
                                    inputs=[reroll_target, card_state, one, parts, note, saved, card_index],
                                    outputs=[one, parts, note, card_state, saved, reroll_status],
                                    concurrency_limit=1,
                                    concurrency_id="partial-reroll",
                                )
                                with gr.Row():
                                    gr.Button("解説をコピー", size="sm")
                                    gr.Button("1行をコピー", size="sm")
                                    gr.Button("パートをコピー", size="sm")
                                    make = gr.Button("生成", size="sm", variant="primary")
                                image_status = gr.Markdown()
                                image_frame = gr.Gallery(
                                    value=None,
                                    columns=2,
                                    allow_preview=True,
                                    object_fit="contain",
                                    height=720,
                                    show_label=False,
                                    elem_classes=["preview-slot"],
                                )
                                make.click(
                                    _forge_one,
                                    inputs=[
                                        one,
                                        negative,
                                        forge_url,
                                        forge_width,
                                        forge_height,
                                        forge_steps,
                                        forge_cfg,
                                        forge_distilled,
                                        forge_sampler,
                                        forge_seed,
                                        forge_batch,
                                    ],
                                    outputs=[image_frame, image_status, forge_saved],
                                    concurrency_limit=1,
                                )

                    with gr.Accordion("ネガティブ", open=False):
                        negative.render()
                        gr.Button("ネガティブをコピー", size="sm")

            inputs = [
                count,
                seed,
                randomize,
                person,
                cameras,
                shots,
                lights,
                poses,
                expressions,
                outfit_pools,
                hair_pools,
                acc_pools,
                seasons,
                prop_mode,
                prop_max,
                backgrounds,
                presences,
                lock_camera,
                lock_shot,
                lock_pose,
                lock_expression,
                lock_hair,
                lock_acc,
                lock_outfit,
                lock_prop,
                lock_bg,
                lock_light,
                finish_key,
                finish_strength,
                wear_hair_accessory,
                wear_earrings,
                wear_neckwear,
                wear_wristwear,
                wear_handwear,
                wear_legwear,
                wear_footwear,
                wear_extra_accessory,
                wear_halo,
                wear_backwear,
                wear_tail,
                costume_key,
            ]
            forge_inputs = [
                forge_url,
                forge_width,
                forge_height,
                forge_steps,
                forge_cfg,
                forge_distilled,
                forge_sampler,
                forge_seed,
                forge_batch,
            ]
            go.click(on_generate, inputs=inputs, outputs=[notes, negative, prompt_state, saved, seed])
            go.click(_pack_forge, inputs=forge_inputs, outputs=[forge_saved])

            def restore(payload):
                skips = tuple(gr.skip() for _ in inputs) + (gr.skip(), gr.skip(), gr.skip())
                if not isinstance(payload, dict) or "count" not in payload:
                    return skips
                items = payload.get("items")
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    items = gr.skip()
                if payload.get("effect_key"):
                    items = []
                if payload.get("finish_key") and payload.get("finish_key") not in {b.key for b in lib.by_slot("finish")} :
                    items = []
                if payload.get("wardrobe_version") != 2:
                    items = []
                known = payload.get("known") if isinstance(payload.get("known"), dict) else {}
                camera_order = [key for _, key in camera_choices]
                shot_order = [key for _, key in shot_choices]
                light_order = [key for _, key in light_choices]
                pose_order = [key for _, key in pose_choices]
                expression_order = [key for _, key in expression_choices]
                saved_presences = (
                    list(DEFAULT_PRESENCES)
                    if "presences" not in payload
                    else list(_clean(_as_list(payload.get("presences")), set(PRESENCE_LABEL)))
                )
                return (
                    max(1, min(20, _int(payload.get("count"), 4))),
                    _int(payload.get("seed"), 1),
                    bool(payload.get("randomize")),
                    payload.get("person") or "",
                    _merge_new(payload.get("cameras"), known.get("cameras"), camera_order, include_new=True),
                    _merge_new(payload.get("shots"), known.get("shots"), shot_order, include_new=False),
                    _merge_new(payload.get("lights"), known.get("lights"), light_order, include_new=True),
                    _merge_new(payload.get("poses"), known.get("poses"), pose_order, include_new=True),
                    _merge_new(payload.get("expressions"), known.get("expressions"), expression_order, include_new=True),
                    _expand_pools(payload.get("outfit_pools")),
                    _expand_pools(payload.get("hair_pools")),
                    _expand_pools(payload.get("acc_pools")),
                    list(_clean(_as_list(payload.get("seasons")), set(SEASON_LABEL))),
                    payload.get("prop_mode") if payload.get("prop_mode") in {"off", "pop"} else "off",
                    max(1, min(3, _int(payload.get("prop_max"), 1))),
                    _merge_new(payload.get("backgrounds"), known.get("backgrounds"), list(bg_categories), include_new=True),
                    saved_presences,
                    payload.get("lock_camera") if payload.get("lock_camera") in camera_keys else "",
                    payload.get("lock_shot") if payload.get("lock_shot") in shot_keys else "",
                    payload.get("lock_pose") if payload.get("lock_pose") in pose_keys else "",
                    payload.get("lock_expression") if payload.get("lock_expression") in expression_keys else "",
                    payload.get("lock_hair") if payload.get("lock_hair") in {block.key for block in hair_blocks} else "",
                    payload.get("lock_acc") if payload.get("lock_acc") in {block.key for block in acc_blocks} else "",
                    payload.get("lock_outfit") if payload.get("lock_outfit") in {block.key for block in outfit_blocks} else "",
                    payload.get("lock_prop") if payload.get("lock_prop") in {block.key for block in prop_blocks} else "",
                    payload.get("lock_bg") if payload.get("lock_bg") in {block.key for block in bg_blocks} else "",
                    payload.get("lock_light") if payload.get("lock_light") in light_keys else "",
                    payload.get("finish_key") if payload.get("finish_key") in {b.key for b in lib.by_slot("finish")} else "",
                    payload.get("finish_strength") if payload.get("finish_strength") in {"weak", "standard", "strong"} else "standard",
                    (payload.get("wear_parts") or {}).get("hair_accessory", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("hair_accessory", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("hair_accessory"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("earrings", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("earrings", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("earrings"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("neckwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("neckwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("neckwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("wristwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("wristwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("wristwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("handwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("handwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("handwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("legwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("legwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("legwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("footwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("footwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("footwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("extra_accessory", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("extra_accessory", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("extra_accessory"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("halo", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("halo", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("halo"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("backwear", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("backwear", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("backwear"))} else "inherit",
                    (payload.get("wear_parts") or {}).get("tail", "inherit") if isinstance(payload.get("wear_parts"), dict) and (payload.get("wear_parts") or {}).get("tail", "inherit") in {"inherit", "none", "random", *(b.key for b in lib.by_slot("tail"))} else "inherit",
                    payload.get("costume_key") if payload.get("costume_key") in {"", "random", *(b.key for b in lib.by_slot("costume"))} else "",
                    payload.get("notes") or "",
                    payload.get("negative") or initial[1],
                    items,
                )

            demo.load(restore, inputs=[saved], outputs=[*inputs, notes, negative, prompt_state])
            demo.load(_restore_forge, inputs=[forge_saved], outputs=forge_inputs)
            def camera_labels(capture_key, current, locked):
                active = capture_key in {b.key for b in lib.by_slot("finish")}
                choices = [(f"{b.block_id} — {b.view_ja or '角度指定なし'}" if active else f"{b.block_id} — {b.title}", b.key)
                           for b in lib.by_slot("camera")]
                return (gr.update(choices=choices, value=current),
                        gr.update(choices=[("ランダム", "")] + choices, value=locked))

            finish_key.change(camera_labels, inputs=[finish_key, cameras, lock_camera], outputs=[cameras, lock_camera])

        with gr.Tab("カテゴリ別件数"):
            gr.Markdown(_library_counts(lib))
    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose gravure prompt text in a local page.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7871)
    args = parser.parse_args()
    demo = _build(PromptLibrary())
    demo.launch(server_name=args.host, server_port=args.port, show_error=True)


if __name__ == "__main__":
    main()
