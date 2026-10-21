"""Load prompts/gravure markdown and compose prompt text."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

BLOCK_RE = re.compile(r"^\*\*(?P<id>[A-Za-z0-9_-]+)\s*[—–-]\s*(?P<title>.+?)\*\*\s*$")
H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
META_RE = re.compile(r"^(?P<key>slot|pool|category|flag|season|presence|view|view_ja|wear):\s*(?P<value>.+?)\s*$")
FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]*)\s*$")

TODDLER_TERMS = ("幼児", "保育園", "園児")
KEY_PREFIX = {
    "camera": "cam",
    "shot": "shot",
    "pose": "pose",
    "expression": "expr",
    "hair": "hair",
    "accessory": "acc",
    "hair_accessory": "hair_accessory",
    "earrings": "earrings",
    "neckwear": "neckwear",
    "wristwear": "wristwear",
    "handwear": "handwear",
    "legwear": "legwear",
    "footwear": "footwear",
    "extra_accessory": "extra_accessory",
    "halo": "halo",
    "backwear": "backwear",
    "tail": "tail",
    "outfit": "outfit",
    "costume": "costume",
    "prop": "prop",
    "background": "bg",
    "lighting": "light",
    "effect": "fx",
    "finish": "finish",
    "negative": "neg",
}
SLOT_LABEL = {
    "camera": "カメラ",
    "shot": "構図",
    "pose": "ポーズ",
    "expression": "表情",
    "hair": "ヘア",
    "accessory": "アクセサリ",
    "hair_accessory": "髪飾り",
    "earrings": "耳飾り",
    "neckwear": "首元",
    "wristwear": "手首",
    "handwear": "手・手袋",
    "legwear": "脚まわり",
    "footwear": "靴",
    "extra_accessory": "その他の装飾・バッグ",
    "halo": "天使の輪",
    "backwear": "背中・羽",
    "tail": "しっぽ",
    "outfit": "衣装",
    "costume": "コスチューム",
    "prop": "小道具",
    "background": "背景",
    "lighting": "ライティング",
    "effect": "演出",
    "finish": "撮影質感",
    "negative": "ネガティブ",
}
WEAR_LABEL = {'hair_accessory': '髪飾り', 'earrings': '耳飾り', 'neckwear': '首元', 'wristwear': '手首', 'handwear': '手・手袋', 'legwear': '脚まわり', 'footwear': '靴', 'extra_accessory': 'その他の装飾・バッグ', 'halo': '天使の輪', 'backwear': '背中・羽', 'tail': 'しっぽ'}
WEAR_NONE = {'hair_accessory': ('No decorative hair accessories or hats.', '髪飾りや帽子は付けません。'), 'earrings': ('No earrings or ear cuffs.', '耳飾りは付けません。'), 'neckwear': ('No necklaces, chokers, costume collars, decorative neck ribbons or scarves.', 'ネックレス・チョーカー・コスプレ用の首輪・装飾リボン・スカーフは付けません。'), 'wristwear': ('No wristwatch, bracelets or bangles.', '腕時計・ブレスレット・バングルは付けません。'), 'handwear': ('No gloves, paw mittens or finger rings.', '手袋・猫の手のミトン・指輪は付けません。'), 'legwear': ('No stockings, tights, socks or anklets.', 'ストッキング・タイツ・靴下・アンクレットは着けません。'), 'footwear': ('She is barefoot.', '裸足です。'), 'extra_accessory': ('No bags, brooches or body chains.', 'バッグ・ブローチ・ボディチェーンは付けません。'), 'halo': ('No halo or floating ring above the head.', '頭上の輪は付けません。'), 'backwear': ('No costume wings or back ornaments.', '背中の羽や飾りは付けません。'), 'tail': ('No costume tail.', 'しっぽは付けません。')}

POOL_LABEL = {
    "hosiery": "ホーズ",
    "tailored": "テーラード",
    "knit": "ニット",
    "dress": "ドレス",
    "evening": "イブニング",
    "swim": "水着",
    "casual": "カジュアル",
    "neat": "きれいめ",
    "maid": "メイド",
    "wa": "和装",
    "stage": "ステージ",
    "classic": "クラシカル",
    "girly": "ガーリー",
    "motif": "モチーフ",
    "pop": "ポップ",
}
SEASON_LABEL = {
    "spring": "春",
    "summer": "夏",
    "autumn": "秋",
    "winter": "冬",
}
PRESENCE_LABEL = {
    "none": "無人",
    "few": "人が少ない",
    "many": "人が多い",
}
# When a season is selected, these slots prefer seasonal blocks.
# Backgrounds do that per place: a place with a seasonal block drops its all-year blocks,
# and a place with none keeps them. Lighting drops every all-year block.
SEASON_EXCLUSIVE = frozenset({"background", "lighting"})
SEASON_EXCLUSIVE_BY_CATEGORY = frozenset({"background"})


@dataclass(frozen=True)
class Block:
    slot: str
    block_id: str
    title: str
    text: str
    ja: str
    pools: tuple[str, ...]
    seasons: tuple[str, ...]
    presences: tuple[str, ...]
    category: str
    source: str
    flags: tuple[str, ...]
    wear: tuple[str, ...] = ()
    view: str = ""
    view_ja: str = ""
    section: str = ""

    @property
    def key(self) -> str:
        prefix = KEY_PREFIX.get(self.slot, self.slot)
        return f"{prefix}/{self.block_id}"


@dataclass
class Options:
    count: int = 4
    seed: int = 1
    person: str = ""
    camera_keys: tuple[str, ...] = ()
    shot_keys: tuple[str, ...] = ()
    pose_keys: tuple[str, ...] = ()
    expression_keys: tuple[str, ...] = ()
    light_keys: tuple[str, ...] = ()
    outfit_pools: tuple[str, ...] = ()
    costume_key: str = ""
    hair_pools: tuple[str, ...] = ()
    accessory_pools: tuple[str, ...] = ()
    wear_parts: dict[str, str] = field(default_factory=dict)
    effect_key: str = ""
    finish_key: str = ""
    finish_strength: str = "standard"
    prop_mode: str = "off"
    prop_max: int = 1
    background_categories: tuple[str, ...] = ()
    seasons: tuple[str, ...] = ()
    presences: tuple[str, ...] = ()
    locks: dict[str, str] = field(default_factory=dict)


@dataclass
class Generation:
    parts: str
    one_line: str
    negative: str
    notes: str
    items: list[tuple[str, str, str]] = field(default_factory=list)
    row_items: list[list[tuple[str, str, str, str]]] = field(default_factory=list)


class PromptLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parent).resolve()
        self.blocks: dict[str, Block] = {}
        self._load()

    def _load(self) -> None:
        if not self.root.is_dir():
            raise FileNotFoundError(f"Prompt directory not found: {self.root}")
        for path in sorted(self.root.rglob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            self._load_file(path)

    def _load_file(self, path: Path) -> None:
        section = {"title": "", "slot": "", "pools": (), "seasons": (), "presences": (), "category": "", "flags": ()}
        pending: dict | None = None
        in_fence = False
        fence_lang = ""
        fence: list[str] = []

        def flush() -> None:
            nonlocal pending
            if pending is None:
                return
            text = str(pending.get("text") or "").strip()
            if text:
                self._register(path, pending, text, section["title"])
            pending = None

        for line in path.read_text(encoding="utf-8").splitlines():
            if in_fence:
                if FENCE_RE.match(line.strip()):
                    body = "\n".join(fence).strip()
                    if pending is not None:
                        if fence_lang == "ja":
                            pending["ja"] = body
                        else:
                            pending["text"] = body
                    in_fence = False
                    fence = []
                    fence_lang = ""
                else:
                    fence.append(line)
                continue
            opened = FENCE_RE.match(line.strip())
            if opened:
                if pending is None:
                    continue
                in_fence = True
                fence_lang = opened.group("lang") or ""
                fence = []
                continue
            heading = H2_RE.match(line.strip())
            if heading:
                flush()
                section = {
                    "title": heading.group("title").strip(),
                    "slot": "",
                    "pools": (),
                    "seasons": (),
                    "presences": (),
                    "category": "",
                    "flags": (),
                }
                continue
            meta = META_RE.match(line.strip())
            if meta:
                target = pending if pending is not None else section
                _apply_meta(target, meta.group("key"), meta.group("value"))
                continue
            header = BLOCK_RE.match(line.strip())
            if header:
                flush()
                pending = {
                    "id": header.group("id"),
                    "title": header.group("title").strip(),
                    "slot": section["slot"],
                    "pools": section["pools"],
                    "seasons": section["seasons"],
                    "presences": section["presences"],
                    "category": section["category"],
                    "flags": section["flags"],
                }
        if in_fence:
            raise ValueError(f"Unclosed code fence in {path}")
        flush()

    def _register(self, path: Path, pending: dict, text: str, section_title: str) -> None:
        slot = str(pending.get("slot") or "")
        title = str(pending.get("title") or "")
        flags = tuple(pending.get("flags") or ())
        if _is_toddler(section_title, title, flags):
            return
        if not slot or not text:
            raise ValueError(f"Block {title!r} in {path} needs a slot and a code block")
        if slot not in KEY_PREFIX:
            raise ValueError(f"Unknown slot {slot!r} in {path}")
        category = str(pending.get("category") or "")
        if slot == "background" and not category:
            category = section_title
        block = Block(
            slot=slot,
            block_id=str(pending["id"]),
            title=title,
            text=text,
            ja=str(pending.get("ja") or ""),
            pools=tuple(pending.get("pools") or ()),
            seasons=_known_seasons(tuple(pending.get("seasons") or ()), title, path),
            presences=_known_presences(tuple(pending.get("presences") or ()), title, path),
            category=category,
            source=str(path),
            flags=flags,
            wear=tuple(pending.get("wear") or ()),
            view=str(pending.get("view") or ""),
            view_ja=str(pending.get("view_ja") or ""),
            section=section_title,
        )
        if block.key in self.blocks:
            other = self.blocks[block.key].source
            raise ValueError(f"Duplicate key {block.key} in {path} and {other}")
        self.blocks[block.key] = block

    def by_slot(self, slot: str) -> list[Block]:
        return sorted((block for block in self.blocks.values() if block.slot == slot), key=lambda block: block.key)

    def categories(self, slot: str) -> list[str]:
        return sorted({block.category for block in self.by_slot(slot) if block.category})

    def get(self, key: str) -> Block:
        try:
            return self.blocks[key]
        except KeyError as exc:
            raise KeyError(f"Unknown block: {key}") from exc


def _apply_meta(target: dict, key: str, value: str) -> None:
    if key == "wear":
        target[key] = tuple(part.strip() for part in value.split(",") if part.strip())
    elif key in {"view", "view_ja"}:
        target[key] = value.strip()
    elif key == "slot":
        target["slot"] = value.strip()
    elif key == "category":
        target["category"] = value.strip()
    elif key == "pool":
        target["pools"] = tuple(part.strip() for part in value.split(",") if part.strip())
    elif key == "season":
        target["seasons"] = tuple(part.strip() for part in value.split(",") if part.strip())
    elif key == "presence":
        target["presences"] = tuple(part.strip() for part in value.split(",") if part.strip())
    elif key == "flag":
        target["flags"] = tuple(part.strip() for part in value.split(",") if part.strip())


def _is_toddler(section_title: str, block_title: str, flags: tuple[str, ...]) -> bool:
    blob = f"{section_title}\n{block_title}\n{' '.join(flags)}"
    if "toddler" in blob.casefold():
        return True
    return any(term in blob for term in TODDLER_TERMS)


def _as_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(value) for value in values if value)


def _known_seasons(seasons: tuple[str, ...], title: str, path: Path) -> tuple[str, ...]:
    unknown = [season for season in seasons if season not in SEASON_LABEL]
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"Unknown season {names} on {title!r} in {path}")
    return seasons


def _known_presences(presences: tuple[str, ...], title: str, path: Path) -> tuple[str, ...]:
    unknown = [presence for presence in presences if presence not in PRESENCE_LABEL]
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"Unknown presence {names} on {title!r} in {path}")
    return presences


def _presence_of(block: Block) -> tuple[str, ...]:
    return block.presences or ("none",)


def _apply_season(
    items: list[Block],
    seasons: tuple[str, ...],
    *,
    exclusive: bool,
    per_category: bool = False,
) -> list[Block]:
    if not seasons:
        return [block for block in items if not block.seasons]
    wanted = set(seasons)
    matched = [block for block in items if wanted.intersection(block.seasons)]
    plain = [block for block in items if not block.seasons]
    if exclusive and matched:
        if not per_category:
            return matched
        covered = {block.category for block in matched}
        return matched + [block for block in plain if block.category not in covered]
    return matched + plain


def _candidates(
    lib: PromptLibrary,
    slot: str,
    *,
    keys: tuple[str, ...] | None = None,
    pools: tuple[str, ...] | None = None,
    categories: tuple[str, ...] | None = None,
    seasons: tuple[str, ...] | None = None,
    presences: tuple[str, ...] | None = None,
) -> list[Block]:
    items = lib.by_slot(slot)
    if keys is not None:
        wanted = set(keys)
        items = [block for block in items if block.key in wanted]
    if pools is not None:
        wanted = set(pools)
        items = [block for block in items if wanted.intersection(block.pools)]
    if categories is not None:
        wanted = set(categories)
        items = [block for block in items if block.category in wanted]
    if presences is not None:
        wanted = set(presences)
        items = [block for block in items if wanted.intersection(_presence_of(block))]
    if seasons is None:
        return items
    return _apply_season(
        items,
        seasons,
        exclusive=slot in SEASON_EXCLUSIVE,
        per_category=slot in SEASON_EXCLUSIVE_BY_CATEGORY,
    )


def _notes(lib: PromptLibrary, options: Options) -> str:
    lines: list[str] = []
    checks = (
        ("outfit", options.outfit_pools),
        ("hair", options.hair_pools),
        ("accessory", options.accessory_pools),
    )
    for slot, pools in checks:
        if not pools:
            continue
        if _candidates(lib, slot, pools=pools, seasons=options.seasons):
            continue
        names = "、".join(POOL_LABEL.get(pool, pool) for pool in pools)
        lines.append(f"{SLOT_LABEL[slot]}: {names} の候補はまだありません")
    if (
        options.prop_mode == "pop"
        and not options.locks.get("prop")
        and not _candidates(lib, "prop", pools=("pop",), seasons=options.seasons)
    ):
        lines.append("小道具: ポップの候補はまだありません")
    if (
        options.background_categories
        and not options.locks.get("background")
        and not _candidates(
            lib,
            "background",
            categories=options.background_categories,
            seasons=options.seasons,
            presences=options.presences,
        )
    ):
        lines.append("背景: 選んだカテゴリの候補はまだありません")
    for slot, key in options.locks.items():
        if key and key not in lib.blocks:
            lines.append(f"{SLOT_LABEL.get(slot, slot)}: {key} は見当たりません")
    if not lib.by_slot("negative"):
        lines.append("ネガティブのブロックがありません")
    return "\n".join(f"- {line}" for line in lines)


def _locked(lib: PromptLibrary, options: Options, slot: str) -> Block | None:
    key = options.locks.get(slot) or ""
    if not key:
        return None
    return lib.blocks.get(key)


def _draw_one(lib: PromptLibrary, rng: random.Random, options: Options) -> list[tuple[str, str, str, str]]:
    """Return (header, key, text, ja) rows. Scene rows are grouped later."""
    rows: list[tuple[str, str, str, str]] = []
    capture = lib.blocks.get(options.finish_key)
    if capture is not None and capture.slot != "finish":
        capture = None
    person = options.person.strip()
    if person:
        rows.append(("人物", "", person, f"人物の指定は「{person}」です。"))

    def add_single(slot: str, header: str, candidates: list[Block]) -> None:
        locked = _locked(lib, options, slot)
        if locked is not None:
            if locked.slot == slot:
                add_block(slot, header, locked)
            return
        if not candidates:
            return
        block = rng.choice(sorted(candidates, key=lambda item: item.key))
        add_block(slot, header, block)

    def add_block(slot: str, header: str, block: Block) -> None:
        if slot == "camera" and capture is not None:
            # Never keep a conflicting focal length/color grade as a fallback.
            if block.view:
                rows.append(("カメラ角度", block.key, block.view, block.view_ja))
            return
        rows.append((header, block.key, block.text, block.ja))

    def narrowed(slot: str, candidates: list[Block]) -> list[Block]:
        return _apply_season(
            candidates,
            options.seasons,
            exclusive=slot in SEASON_EXCLUSIVE,
            per_category=slot in SEASON_EXCLUSIVE_BY_CATEGORY,
        )

    add_single("camera", "カメラ", narrowed("camera", _candidates(lib, "camera", keys=options.camera_keys)))
    add_single("shot", "構図", narrowed("shot", _candidates(lib, "shot", keys=options.shot_keys)))
    add_single("pose", "ポーズ", narrowed("pose", _candidates(lib, "pose", keys=options.pose_keys)))
    add_single(
        "expression",
        "表情",
        narrowed("expression", _candidates(lib, "expression", keys=options.expression_keys)),
    )
    add_single(
        "hair",
        "ヘア",
        narrowed("hair", _candidates(lib, "hair", pools=options.hair_pools)) if options.hair_pools else [],
    )
    costume = lib.blocks.get(options.costume_key)
    if options.costume_key == "random":
        costumes = lib.by_slot("costume")
        costume = rng.choice(costumes) if costumes else None
    if costume is not None and costume.slot == "costume":
        rows.append(("コスチューム", costume.key, costume.text, costume.ja))
    else:
        costume = None
        add_single(
            "outfit", "衣装",
            narrowed("outfit", _candidates(lib, "outfit", pools=options.outfit_pools)) if options.outfit_pools else [],
        )

    inherited: dict[str, Block] = {}
    for _, selected_key, _, _ in rows:
        owner = lib.blocks.get(selected_key)
        if owner is not None:
            if costume is not None and owner.slot == "hair":
                continue
            for part_key in owner.wear:
                part = lib.blocks.get(part_key)
                if part is not None and part.slot in WEAR_LABEL:
                    inherited[part.slot] = part
    for slot, label in WEAR_LABEL.items():
        choice = options.wear_parts.get(slot, "inherit")
        if choice == "none":
            text, ja = WEAR_NONE[slot]
            rows.append((label, "", text, ja))
            continue
        if choice == "inherit":
            part = inherited.get(slot)
        elif choice == "random":
            pools = options.hair_pools if slot in {"hair_accessory", "halo"} else options.outfit_pools
            if costume is not None:
                pools = costume.pools
            candidates = _candidates(lib, slot, seasons=options.seasons)
            if pools:
                candidates = [b for b in candidates if not b.pools or set(pools).intersection(b.pools)]
            part = rng.choice(sorted(candidates, key=lambda b: b.key)) if candidates else None
        else:
            part = lib.blocks.get(choice)
            if part is not None and part.slot != slot:
                part = None
        if part is not None:
            rows.append((label, part.key, part.text, part.ja))

    scene: list[tuple[str, str, str]] = []
    locked_prop = _locked(lib, options, "prop")
    if locked_prop is not None and locked_prop.slot == "prop":
        scene.append((locked_prop.key, locked_prop.text, locked_prop.ja))
    elif options.prop_mode == "pop":
        props = sorted(_candidates(lib, "prop", pools=("pop",), seasons=options.seasons), key=lambda item: item.key)
        if props:
            count = rng.randint(1, min(max(options.prop_max, 1), len(props)))
            for block in rng.sample(props, count):
                scene.append((block.key, block.text, block.ja))

    locked_bg = _locked(lib, options, "background")
    if locked_bg is not None and locked_bg.slot == "background":
        scene.append((locked_bg.key, locked_bg.text, locked_bg.ja))
    elif options.background_categories:
        backgrounds = _candidates(
            lib,
            "background",
            categories=options.background_categories,
            seasons=options.seasons,
            presences=options.presences,
        )
        if backgrounds:
            block = rng.choice(sorted(backgrounds, key=lambda item: item.key))
            scene.append((block.key, block.text, block.ja))

    if capture is None or "flash" not in capture.flags:
        locked_light = _locked(lib, options, "lighting")
        if locked_light is not None and locked_light.slot == "lighting":
            scene.append((locked_light.key, locked_light.text, locked_light.ja))
        elif options.light_keys:
            lights = _candidates(lib, "lighting", keys=options.light_keys, seasons=options.seasons)
            if lights:
                block = rng.choice(sorted(lights, key=lambda item: item.key))
                scene.append((block.key, block.text, block.ja))

    if scene:
        keys = ", ".join(key for key, _, _ in scene)
        body = "\n".join(text for _, text, _ in scene)
        note = "\n\n".join(item for _, _, item in scene if item)
        rows.append(("シーン", keys, body, note))
    effect = lib.blocks.get(options.effect_key)
    if effect is not None and effect.slot == "effect":
        rows.append(("演出", effect.key, effect.text, effect.ja))
    if capture is not None:
        strength = {
            "weak": ("Keep the characteristic color response, with only slight grain, noise or optical softness.", "発色の特徴は残し、粒子・ノイズ・光学的な柔らかさは控えめにします。"),
            "standard": ("Show clearly recognizable capture characteristics in color, tonal response and fine detail.", "発色・階調・細部に、撮影方式の特徴をはっきり出します。"),
            "strong": ("Make the characteristic color response, grain or sensor noise, highlight behavior and optical imperfections pronounced throughout the image.", "発色、粒子やセンサーノイズ、明部の階調、光学的な不完全さを画面全体に強く出します。"),
        }.get(options.finish_strength)
        if strength is None:
            strength = ("Show clearly recognizable capture characteristics.", "撮影方式の特徴をはっきり出します。")
        rows.insert(0, ("撮影質感", capture.key, capture.text + " " + strength[0], capture.ja + " " + strength[1]))
    return rows


def _format_one(rows: list[tuple[str, str, str, str]]) -> tuple[str, str, str]:
    parts: list[str] = []
    sentences: list[str] = []
    notes: list[str] = []
    for header, key, text, note in rows:
        title = f"# {header}"
        if key:
            title += f" ({key})"
        parts.append(f"{title}\n{text}")
        sentences.append(text.replace("\n", " "))
        if note:
            notes.append(note)
    return "\n\n".join(parts), " ".join(sentences), "\n\n".join(notes)


def generate(lib: PromptLibrary, options: Options) -> Generation:
    count = min(20, max(1, int(options.count)))
    rng = random.Random(int(options.seed))
    blocks: list[str] = []
    lines: list[str] = []
    items: list[tuple[str, str, str]] = []
    row_items = []
    for index in range(1, count + 1):
        rows = _draw_one(lib, rng, options)
        row_items.append(rows)
        parts, one_line, note = _format_one(rows)
        items.append((parts, one_line, note))
        blocks.append(f"[{index}]\n\n{parts}" if parts else f"[{index}]")
        lines.append(f"[{index}] {one_line}".rstrip())
    negative = "\n".join(block.text for block in lib.by_slot("negative"))
    return Generation(
        parts="\n\n---\n\n".join(blocks),
        one_line="\n".join(lines),
        negative=negative,
        notes=_notes(lib, options),
        items=items,
        row_items=row_items,
    )


def reroll_part(lib: PromptLibrary, rows, options: Options, slot: str, seed: int):
    """Replace only the requested part; leave all other rows unchanged."""
    supported = {"camera", "shot", "pose", "expression", "hair", "outfit", "prop", "background", "lighting", *WEAR_LABEL}
    if slot not in supported:
        raise ValueError("このパートは部分変更に対応していません。")
    rows = [tuple(row) for row in rows]
    selected = [key.strip() for _, keys, _, _ in rows for key in keys.split(",") if key.strip()]
    current_costume = next((lib.blocks[k] for k in selected if k in lib.blocks and lib.blocks[k].slot == "costume"), None)
    candidate_slot = "costume" if slot == "outfit" and current_costume is not None else slot
    old_keys = {key for key in selected if key in lib.blocks and lib.blocks[key].slot == candidate_slot}
    kwargs = {"seasons": options.seasons}
    key_field = {"camera": "camera_keys", "shot": "shot_keys", "pose": "pose_keys", "expression": "expression_keys", "lighting": "light_keys"}.get(slot)
    if key_field:
        wanted = getattr(options, key_field)
        if wanted:
            kwargs["keys"] = wanted
    if slot in {"hair", "outfit"}:
        pools = options.hair_pools if slot == "hair" else options.outfit_pools
        if pools:
            kwargs["pools"] = pools
    elif slot in WEAR_LABEL:
        pools = options.hair_pools if slot in {"hair_accessory", "halo"} else options.outfit_pools
        if current_costume is not None:
            pools = current_costume.pools
        if pools:
            kwargs["pools"] = pools
    elif slot == "background":
        if options.background_categories:
            kwargs["categories"] = options.background_categories
        kwargs["presences"] = options.presences
    elif slot == "prop":
        kwargs["pools"] = ("pop",)
    capture = lib.blocks.get(options.finish_key)
    if slot == "lighting" and capture is not None and "flash" in capture.flags:
        raise ValueError("直射フラッシュの撮影質感が照明を決めています。撮影質感を変更してください。")
    if candidate_slot == "costume":
        kwargs = {"categories": (current_costume.category,), "seasons": options.seasons}
    candidates = [b for b in _candidates(lib, candidate_slot, **kwargs) if b.key not in old_keys]
    if slot == "camera" and capture is not None and capture.slot == "finish":
        candidates = [b for b in candidates if b.view]
    # Keep repeated clicks from returning the same visual camera angle.
    if slot == "camera" and capture is not None and capture.slot == "finish":
        old_views = {lib.blocks[k].view for k in old_keys}
        candidates = [b for b in candidates if b.view not in old_views]
    if not candidates:
        raise ValueError("作成時の条件に、現在と異なる候補がありません。左の条件を変えて作り直してください。")
    rng = random.Random(seed)
    scene_slots = {"prop", "background", "lighting"}
    if slot in scene_slots:
        count = max(1, len(old_keys)) if slot == "prop" else 1
        if len(candidates) < count:
            raise ValueError("同じ小道具数を保って変更する候補が足りません。")
        picked = rng.sample(sorted(candidates, key=lambda b: b.key), count)
        scene_index = next((i for i,row in enumerate(rows) if row[0] == "シーン"), None)
        scene_keys = [k.strip() for k in rows[scene_index][1].split(",") if k.strip()] if scene_index is not None else []
        # Scene rows are made entirely from source blocks by _draw_one.
        if any(k not in lib.blocks for k in scene_keys):
            raise ValueError("背景データが変更されています。プロンプトを作り直してください。")
        if scene_index is not None:
            expected_text = "\n".join(lib.blocks[k].text for k in scene_keys)
            expected_note = "\n\n".join(lib.blocks[k].ja for k in scene_keys if lib.blocks[k].ja)
            if rows[scene_index][2:] != (expected_text, expected_note):
                raise ValueError("シーンの元データが変更されています。他のパートを保つため、プロンプトを作り直してください。")
        scene_blocks = []
        inserted = False
        for key in scene_keys:
            block = lib.blocks[key]
            if block.slot == slot:
                if not inserted:
                    scene_blocks.extend(picked)
                    inserted = True
            else:
                scene_blocks.append(block)
        if not inserted:
            scene_blocks.extend(picked)
        row = ("シーン", ", ".join(b.key for b in scene_blocks), "\n".join(b.text for b in scene_blocks), "\n\n".join(b.ja for b in scene_blocks if b.ja))
        if scene_index is None:
            rows.append(row)
        else:
            rows[scene_index] = row
    else:
        block = rng.choice(sorted(candidates, key=lambda b: b.key))
        header, text, ja = SLOT_LABEL[candidate_slot], block.text, block.ja
        if slot == "camera" and capture is not None and capture.slot == "finish":
            header, text, ja = "カメラ角度", block.view, block.view_ja
        new_row = (header, block.key, text, ja)
        index = next((i for i,row in enumerate(rows) if row[1] in old_keys or (not row[1] and row[0] == SLOT_LABEL[slot])), None)
        if index is None:
            scene_index = next((i for i,row in enumerate(rows) if row[0] == "シーン"), len(rows))
            rows.insert(scene_index, new_row)
        else:
            rows[index] = new_row
    return rows, _format_one(rows)


def run_checks() -> None:
    lib = PromptLibrary()
    shot_keys = tuple(block.key for block in lib.by_slot("shot"))
    light_keys = tuple(block.key for block in lib.by_slot("lighting"))
    if not shot_keys or not light_keys or not lib.by_slot("negative"):
        raise SystemExit("基本.md needs shots, lighting, and a negative block")
    options = Options(count=4, seed=1, shot_keys=shot_keys, light_keys=light_keys)
    first = generate(lib, options)
    second = generate(lib, options)
    if first.parts != second.parts or first.one_line != second.one_line or first.items != second.items:
        raise SystemExit("same seed did not reproduce the batch")
    if len(first.items) != 4:
        raise SystemExit("expected one item per prompt")
    if "Japanese woman" in first.parts or "# 人物" in first.parts:
        raise SystemExit("empty person field leaked into the prompt")
    named = generate(lib, Options(count=1, seed=1, person="looking at the camera", shot_keys=shot_keys[:1], light_keys=()))
    if "# 人物\nlooking at the camera" not in named.parts:
        raise SystemExit("person text was not inserted as written")
    if "人物の指定は「looking at the camera」です。" not in named.items[0][2]:
        raise SystemExit("person note was not written in Japanese")
    missing = [block.key for block in lib.blocks.values() if block.slot != "negative" and not block.ja]
    if missing:
        raise SystemExit(f"japanese note missing: {missing}")
    if "# シーン" in named.parts or "# 構図" not in named.parts:
        raise SystemExit("shot and lighting selection was not honored")
    locked = generate(
        lib,
        Options(count=3, seed=3, shot_keys=shot_keys, light_keys=light_keys, locks={"lighting": light_keys[0]}),
    )
    if locked.parts.count(light_keys[0]) != 3:
        raise SystemExit("lighting lock was not applied to every prompt")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sample.md").write_text(
            """## 保育園・幼児風
slot: outfit
pool: childish
**P1 — スモック**
```
She wears a smock.
```
## 水着
slot: outfit
pool: gravure
**W1 — 黒**
flag: toddler
```
She wears a black one-piece.
```
## 部屋着
slot: outfit
pool: gravure
**W2 — シャツ**
```
She wears an oversized white shirt.
```
""",
            encoding="utf-8",
        )
        sample = PromptLibrary(root)
        keys = set(sample.blocks)
        if keys != {"outfit/W2"}:
            raise SystemExit(f"toddler filter failed: {keys}")
    outdoor = _candidates(lib, "background", categories=("屋外",), seasons=())
    if any(block.seasons for block in outdoor):
        raise SystemExit("all-year draw included a seasonal background")
    winter_out = _candidates(lib, "background", categories=("屋外",), seasons=("winter",))
    if not winter_out or any("winter" not in block.seasons for block in winter_out):
        raise SystemExit("winter backgrounds were not exclusive")
    summer_beach = _candidates(lib, "background", categories=("ビーチ",), seasons=("summer",))
    if not summer_beach or any(block.seasons for block in summer_beach):
        raise SystemExit("summer draw dropped all-year beaches")
    summer_salon = _candidates(lib, "background", categories=("ダークサロン",), seasons=("summer",))
    if not summer_salon or any("summer" not in block.seasons for block in summer_salon):
        raise SystemExit("summer salon did not replace the all-year salon")
    if _candidates(lib, "outfit", pools=("swim",), seasons=()):
        raise SystemExit("swimwear leaked without summer")
    if not _candidates(lib, "outfit", pools=("swim",), seasons=("summer",)):
        raise SystemExit("summer swimwear was missing")
    if not _candidates(lib, "outfit", pools=("hosiery",), seasons=()):
        raise SystemExit("all-year hosiery was missing")
    if len(lib.by_slot("expression")) < 20:
        raise SystemExit("expression catalog is too small")
    places = set(lib.categories("background"))
    missing_places = [name for name in ("街", "駅", "店", "廊下", "水辺") if name not in places]
    if missing_places:
        raise SystemExit(f"places missing: {missing_places}")
    few = _candidates(lib, "background", categories=("街",), presences=("few",), seasons=())
    many = _candidates(lib, "background", categories=("街",), presences=("many",), seasons=())
    if not few or not many:
        raise SystemExit("street presence split failed")
    winter_many = _candidates(lib, "background", categories=("屋外",), presences=("many",), seasons=("winter",))
    if not winter_many or any("winter" not in block.seasons or "many" not in block.presences for block in winter_many):
        raise SystemExit("winter crowd backgrounds were not exclusive")
    print(f"ok blocks={len(lib.blocks)} shots={len(shot_keys)} lights={len(light_keys)}")
    print(first.one_line)


if __name__ == "__main__":
    run_checks()
