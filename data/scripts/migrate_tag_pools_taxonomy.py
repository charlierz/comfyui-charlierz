#!/usr/bin/env python3
"""Rebuild data/tag_pools into the curated short-root taxonomy.

Sources:
- existing data/tag_pools/**/*.tsv, used to preserve generated seed tags/counts;
- data/tag_wip/**/*.txt, used as curated import material;
- data/danbooru_tags.csv, used to fill missing counts.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_POOLS = DATA_DIR / "tag_pools"
DEFAULT_WIP = DATA_DIR / "tag_wip"
DEFAULT_DANBOORU = DATA_DIR / "danbooru_tags.csv"
TSV_HEADER = ("tag", "count", "related")

TEMPLATE_RE = re.compile(r"__[^_]*(?:_[^_]+)*__")
WEIGHTED_RE = re.compile(r"^\((?P<tag>[^:()]+):[0-9.]+\)$")
BAD_TOKENS = ("{", "}", "|", "__", "\t")


@dataclass
class TagRow:
    count: int | None = None
    related: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)


@dataclass
class Stats:
    source_rows: int = 0
    rows_added: int = 0
    rows_skipped: int = 0
    duplicate_rows: int = 0
    files_written: int = 0
    rows_written: int = 0


PoolMap = dict[str, dict[str, TagRow]]


EXISTING_POOL_MAP = {
    "angle.tsv": "camera/angle.tsv",
    "perspective.tsv": "camera/perspective.tsv",
    "positions.tsv": "__classify_position__",
    "shading.tsv": "style/shading.tsv",
    "styles.tsv": "style/styles.tsv",
    "techniques.tsv": "style/techniques.tsv",
    "colors.tsv": "visual/colors.tsv",
    "bg/buildings.tsv": "scene/bg/places.tsv",
    "bg/color.tsv": "scene/bg/color.tsv",
    "bg/indoors.tsv": "scene/bg/indoors.tsv",
    "bg/outdoors/manmade.tsv": "scene/bg/places.tsv",
    "bg/outdoors/natural.tsv": "scene/bg/nature.tsv",
    "bg/pattern.tsv": "scene/bg/pattern.tsv",
    "body/breasts.tsv": "body/breasts/size.tsv",
    "body/build.tsv": "body/build.tsv",
    "body/penis.tsv": "__classify_penis__",
    "clothes/accessory/head.tsv": "clothes/accessory/head.tsv",
    "clothes/accessory/limbs.tsv": "clothes/accessory/limbs.tsv",
    "clothes/accessory/misc.tsv": "clothes/accessory/misc.tsv",
    "clothes/accessory/neck.tsv": "clothes/accessory/neck.tsv",
    "clothes/details.tsv": "clothes/details.tsv",
    "clothes/full/bodysuit.tsv": "clothes/full/bodysuit.tsv",
    "clothes/full/other.tsv": "clothes/full/other.tsv",
    "clothes/full/swimsuit.tsv": "clothes/full/swimsuit.tsv",
    "clothes/full/traditional.tsv": "clothes/full/traditional.tsv",
    "clothes/full/uniform.tsv": "clothes/full/uniform.tsv",
    "clothes/pants.tsv": "clothes/bottom.tsv",
    "clothes/print.tsv": "visual/patterns.tsv",
    "clothes/sexual/bdsm.tsv": "clothes/sexual/bdsm.tsv",
    "clothes/sexual/bra.tsv": "clothes/sexual/bra.tsv",
    "clothes/sexual/exposure.tsv": "clothes/sexual/exposure.tsv",
    "clothes/sexual/lingerie.tsv": "clothes/sexual/lingerie.tsv",
    "clothes/sexual/panties.tsv": "clothes/sexual/panties.tsv",
    "clothes/shirt.tsv": "clothes/top.tsv",
    "clothes/shoes.tsv": "clothes/footwear.tsv",
    "face/emoticons.tsv": "face/emoticons.tsv",
    "face/emotions.tsv": "face/emotion.tsv",
    "face/negative.tsv": "face/emotion.tsv",
    "face/sexual.tsv": "face/sexual.tsv",
    "face/smile.tsv": "face/mouth.tsv",
    "face/smug.tsv": "face/emotion.tsv",
    "hair/accessory.tsv": "body/hair/accessory.tsv",
    "hair/color.tsv": "body/hair/color.tsv",
    "hair/fantasy.tsv": "body/hair/fantasy.tsv",
    "hair/front.tsv": "body/hair/front.tsv",
    "hair/length.tsv": "body/hair/length.tsv",
    "hair/multicolor.tsv": "body/hair/multicolor.tsv",
    "hair/style.tsv": "body/hair/style.tsv",
    "hair/texture.tsv": "body/hair/texture.tsv",
    "hair/top.tsv": "body/hair/top.tsv",
    "nudity/arms.tsv": "body/exposure/arms.tsv",
    "nudity/chest.tsv": "body/breasts/exposure.tsv",
    "nudity/full.tsv": "body/exposure/full.tsv",
    "nudity/nakedclothes.tsv": "body/exposure/naked_clothes.tsv",
    "nudity/partial.tsv": "clothes/sexual/exposure.tsv",
    "pose/body.tsv": "pose/position.tsv",
    "pose/gesture.tsv": "pose/gesture.tsv",
    "pose/hands.tsv": "pose/hands.tsv",
    "pose/movement.tsv": "pose/movement.tsv",
    "pose/position.tsv": "pose/position.tsv",
    # Idempotence/cleanup mappings after the first migration run.
    "body/breasts/features.tsv": "body/breasts/nipples.tsv",
    "body/penis/size.tsv": "__classify_penis_size__",
    "camera/view/sexual.tsv": "camera/sexual_view.tsv",
    "pose/bdsm.tsv": "pose/action.tsv",
    "pose/positions.tsv": "__classify_position__",
    "pose/sexual.tsv": "__classify_sexual_emotion__",
    "pose/sexual/features.tsv": "pose/action.tsv",
    "pose/sexual/motion.tsv": "pose/motion.tsv",
    "pose/sexual/penis.tsv": "pose/penis.tsv",
    "scene/objects/sexual.tsv": "scene/sexual_objects.tsv",
}

NEW_ROOTS = {"body", "camera", "clothes", "face", "pose", "scene", "style", "theme", "visual"}

WIP_FILE_MAP = {
    "body parts/breast feature.txt": "body/breasts/nipples.tsv",
    "body parts/breast shape.txt": "body/breasts/shape.tsv",
    "body parts/breast size.txt": "body/breasts/size.tsv",
    "body parts/fantasy penis features.txt": "body/penis/fantasy.tsv",
    "body parts/penis acts.txt": "pose/penis.tsv",
    "body parts/penis size.txt": "body/penis/size.tsv",
    "body parts/pussy features.txt": "body/pussy.tsv",
    "body parts/tentacles.txt": "body/tentacles.tsv",
    "colors, pattern and materials/Colors.txt": "visual/colors.tsv",
    "colors, pattern and materials/materials.txt": "visual/materials.tsv",
    "colors, pattern and materials/prints and patterns.txt": "visual/patterns.tsv",
    "compoisiton/background.txt": "scene/background.tsv",
    "compoisiton/body framing.txt": "camera/framing.tsv",
    "compoisiton/compostion.txt": "camera/layout.tsv",
    "compoisiton/errors.txt": "style/errors.tsv",
    "compoisiton/focus.txt": "camera/focus.tsv",
    "compoisiton/Format.txt": "style/format.tsv",
    "compoisiton/misc patterns.txt": "visual/patterns.tsv",
    "compoisiton/perspective.txt": "camera/perspective.tsv",
    "compoisiton/styles.txt": "style/styles.tsv",
    "compoisiton/subject Matter.txt": "scene/subject_matter.tsv",
    "compoisiton/techniques.txt": "style/techniques.tsv",
    "compoisiton/Traditional Japanese Patterns.txt": "visual/japanese_patterns.tsv",
    "compoisiton/view Angle.txt": "camera/angle.tsv",
    "compoisiton/year.txt": "style/year.tsv",
    "nsfw enhancers/bdsm.txt": "pose/action.tsv",
    "nsfw enhancers/cum.txt": "body/fluids/cum.tsv",
    "nsfw enhancers/motion features.txt": "pose/motion.tsv",
    "nsfw enhancers/pussy juice.txt": "body/fluids/pussy_juice.tsv",
    "nsfw enhancers/saliva.txt": "body/fluids/saliva.tsv",
    "nsfw enhancers/sex features.txt": "pose/action.tsv",
    "nsfw enhancers/sexuals objects.txt": "scene/sexual_objects.tsv",
    "nsfw enhancers/sexy clothes.txt": "clothes/sexual/sexy_clothes.tsv",
    "nsfw enhancers/view.txt": "camera/sexual_view.tsv",
    "outfit/armor.txt": "clothes/armor.tsv",
    "outfit/attires descriptions/aesthetic fashion.txt": "clothes/descriptors/aesthetic.tsv",
    "outfit/attires descriptions/attires enhancer.txt": "clothes/descriptors/enhancer.tsv",
    "outfit/attires descriptions/materials.txt": "clothes/descriptors/materials.tsv",
    "outfit/attires descriptions/prints and colors.txt": "clothes/descriptors/prints_colors.tsv",
    "outfit/bandaid.txt": "clothes/bandaid.tsv",
    "outfit/bottom.txt": "clothes/bottom.tsv",
    "outfit/dress.txt": "clothes/dress.tsv",
    "outfit/footwear.txt": "clothes/footwear.tsv",
    "outfit/headgear.txt": "clothes/accessory/head.tsv",
    "outfit/leagwear.txt": "clothes/legwear.tsv",
    "outfit/neckwear.txt": "clothes/accessory/neck.tsv",
    "outfit/sexual attires.txt": "clothes/sexual/lingerie.tsv",
    "outfit/swimsuit.txt": "clothes/full/swimsuit.tsv",
    "outfit/top.txt": "clothes/top.tsv",
    "outfit/Traditional Clothing.txt": "clothes/full/traditional.tsv",
    "outfit/uniform.txt": "clothes/full/uniform.tsv",
    "pose/reijssexyposing.txt": "pose/position.tsv",
}

FACE_EMOTION = {
    "awe",
    "blush",
    "embarrassed",
    "crazy",
    "excited",
    "exhausted",
    "pain",
    "scared",
    "wince",
    "tears",
    "happy tears",
    "crying",
    "crying with eyes open",
    "surprised",
    "flustered",
    "shy",
    "angry",
    "disgust",
    "sobbing",
    "screaming",
}
FACE_GAZE = {
    "facing away",
    "facing ahead",
    "looking to the side",
    "looking ahead",
    "looking up",
    "looking down",
    "looking back",
}
FACE_EYES = {
    "closed eyes",
    "one eye closed",
    "wide-eyed",
    "rolling eyes",
    "cross-eyed",
    "constricted pupils",
    "narrowed eyes",
    "raised eyebrow",
    "raised eyebrows",
    "raised inner eyebrows",
    "paralysis",
}
FACE_MOUTH = {
    "cheek bulge",
    "throat bulge",
    "open mouth",
    "crazy smile",
    "biting own lip",
    "jaw drop",
    "clenched teeth",
    "parted lips",
    "breath",
    "heavy breathing",
    "tongue out",
    "licking lips",
    "open smile",
    "pouting",
    "closed frown",
    "snarling",
    "roaring",
    "yelling",
}
FACE_SEXUAL = {
    "ahegao",
    "super masara ahegao",
    "naughty face",
    "in heat",
    "seductive smile",
    "torogao",
    "bedroom eyes",
    "looking pleasured",
    "moaning",
    "grunting",
    "orgasm face",
    "panting",
    "aroused",
}
BODY_SWEAT = {"sweat", "sweating", "steaming body", "nervous sweating", "sparkling sweat", "very sweaty", "flying sweatdrops"}

BDSM_WORDS = {
    "bound",
    "frogtie",
    "hogtie",
    "cuffs",
    "strappado",
    "suspension",
    "box tie",
}
SEX_POSITION_WORDS = {
    "cowgirl",
    "missionary",
    "doggystyle",
    "spitroast",
    "mating press",
    "prone bone",
    "69",
    "congress",
    "amazon position",
    "piledriver",
    "girl on top",
    "boy on top",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=Path, default=DEFAULT_POOLS)
    parser.add_argument("--wip", type=Path, default=DEFAULT_WIP)
    parser.add_argument("--danbooru-tags", type=Path, default=DEFAULT_DANBOORU)
    parser.add_argument("--force", action="store_true", help="Replace the output pools directory.")
    args = parser.parse_args()

    pools_dir = args.pools.resolve()
    wip_dir = args.wip.resolve()
    counts = read_danbooru_counts(args.danbooru_tags)
    stats = Stats()
    pools: PoolMap = defaultdict(dict)

    read_existing_pools(pools_dir, pools, counts, stats)
    read_wip_pools(wip_dir, pools, counts, stats)

    if args.force and pools_dir.exists():
        shutil.rmtree(pools_dir)
    pools_dir.mkdir(parents=True, exist_ok=True)
    write_pools(pools_dir, pools, stats)

    print(f"Files written: {stats.files_written}")
    print(f"Rows written: {stats.rows_written}")
    print(f"Source rows read: {stats.source_rows}")
    print(f"Rows added from sources: {stats.rows_added}")
    print(f"Duplicate source rows merged: {stats.duplicate_rows}")
    print(f"Rows skipped: {stats.rows_skipped}")


def read_danbooru_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tag = normalize_tag(row.get("tag") or "")
            count_text = (row.get("count") or "").strip()
            if not tag or not count_text:
                continue
            try:
                counts[tag] = int(count_text)
            except ValueError:
                continue
    return counts


def read_existing_pools(
    pools_dir: Path,
    pools: PoolMap,
    danbooru_counts: dict[str, int],
    stats: Stats,
) -> None:
    if not pools_dir.exists():
        return
    for path in sorted(pools_dir.rglob("*.tsv")):
        rel = path.relative_to(pools_dir).as_posix()
        mapping = EXISTING_POOL_MAP.get(rel)
        if mapping is None:
            root = path.relative_to(pools_dir).parts[0]
            if root in NEW_ROOTS:
                mapping = rel
            else:
                stats.rows_skipped += count_tsv_rows(path)
                print(f"Warning: no mapping for existing pool {rel}")
                continue
        for tag, count, related in read_tsv(path):
            stats.source_rows += 1
            destinations = route_existing(mapping, tag)
            if not destinations:
                stats.rows_skipped += 1
                continue
            for dest in destinations:
                add_tag(pools, dest, tag, count, related, rel, danbooru_counts, stats)


def read_wip_pools(
    wip_dir: Path,
    pools: PoolMap,
    danbooru_counts: dict[str, int],
    stats: Stats,
) -> None:
    if not wip_dir.exists():
        return
    for path in sorted(wip_dir.rglob("*.txt")):
        rel = path.relative_to(wip_dir).as_posix()
        mapping = WIP_FILE_MAP.get(rel)
        if mapping is None and rel not in {
            "body parts/bottom body features.txt",
            "body parts/breast acts.txt",
            "body parts/expression.txt",
            "body parts/penis features.txt",
            "nsfw enhancers/sexual emotions.txt",
            "outfit/fullbody attires.txt",
            "outfit/Jewelry and Accessories.txt",
        }:
            print(f"Warning: no mapping for WIP file {rel}")
        for raw in read_txt_entries(path, split_commas=rel == "nsfw enhancers/sexual emotions.txt"):
            stats.source_rows += 1
            tag = clean_tag(raw)
            if not is_simple_tag(tag):
                stats.rows_skipped += 1
                continue
            destinations = route_wip(rel, mapping, tag)
            if not destinations:
                stats.rows_skipped += 1
                continue
            for dest in destinations:
                add_tag(pools, dest, tag, None, "", rel, danbooru_counts, stats)


def read_tsv(path: Path) -> list[tuple[str, int | None, str]]:
    rows: list[tuple[str, int | None, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            tag = clean_tag(row.get("tag") or "")
            if not tag:
                continue
            count = parse_count(row.get("count") or "")
            related = row.get("related") or ""
            rows.append((tag, count, related))
    return rows


def read_txt_entries(path: Path, *, split_commas: bool) -> list[str]:
    entries: list[str] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",") if split_commas else [line]
            entries.extend(parts)
    return entries


def route_existing(mapping: str, tag: str) -> list[str]:
    if mapping == "__classify_penis__":
        return [classify_penis(tag)]
    if mapping == "__classify_penis_size__":
        return [classify_penis_size(tag)]
    if mapping == "__classify_position__":
        return [classify_position(tag)]
    if mapping == "__classify_sexual_emotion__":
        return [classify_sexual_emotion(tag)]
    return [mapping]


def route_wip(rel: str, mapping: str | None, tag: str) -> list[str]:
    if rel == "body parts/bottom body features.txt":
        return [classify_bottom_body(tag)]
    if rel == "body parts/breast acts.txt":
        return [classify_breast_act(tag)]
    if rel == "body parts/expression.txt":
        return [classify_expression(tag)]
    if rel == "body parts/penis size.txt":
        return [classify_penis_size(tag)]
    if rel == "body parts/penis features.txt":
        return [classify_penis_feature(tag)]
    if rel == "nsfw enhancers/sexual emotions.txt":
        return [classify_sexual_emotion(tag)]
    if rel == "outfit/fullbody attires.txt":
        return [classify_fullbody_attire(tag)]
    if rel == "outfit/Jewelry and Accessories.txt":
        return [classify_accessory(tag)]
    return [] if mapping is None else [mapping]


def classify_penis(tag: str) -> str:
    if "testicle" in tag:
        return "body/penis/testicles.tsv"
    if any(word in tag for word in ("large", "huge", "small", "gigantic", "micro", "short", "thin", "girthy")):
        return "body/penis/size.tsv"
    if any(word in tag for word in ("knotted", "spiked", "extra", "glowing", "translucent")):
        return "body/penis/fantasy.tsv"
    return "body/penis/features.tsv"


def classify_penis_size(tag: str) -> str:
    if tag == "penis":
        return "body/penis/features.tsv"
    return "body/penis/size.tsv"


def classify_penis_feature(tag: str) -> str:
    if "testicle" in tag:
        return "body/penis/testicles.tsv"
    return classify_penis(tag)


def classify_position(tag: str) -> str:
    if any(word in tag for word in BDSM_WORDS):
        return "pose/action.tsv"
    return "pose/position.tsv"


def classify_bottom_body(tag: str) -> str:
    if "anus" in tag:
        return "body/anus.tsv"
    if "thigh" in tag or "hip" in tag:
        return "body/thighs.tsv"
    return "body/ass.tsv"


def classify_breast_act(tag: str) -> str:
    if tag in {"areola slip", "nipple slip", "breast slip"}:
        return "body/breasts/exposure.tsv"
    if tag == "breast focus":
        return "camera/focus.tsv"
    if tag == "bouncing breasts":
        return "pose/movement.tsv"
    if tag == "breast expansion":
        return "body/breasts/effects.tsv"
    if "glass" in tag:
        return "pose/body_contact.tsv"
    return "pose/breast_touch.tsv"


def classify_expression(tag: str) -> str:
    if tag in FACE_SEXUAL:
        return "face/sexual.tsv"
    if tag in FACE_EMOTION:
        return "face/emotion.tsv"
    if tag in FACE_GAZE:
        return "face/gaze.tsv"
    if tag in FACE_EYES:
        return "face/eyes.tsv"
    if tag in FACE_MOUTH:
        return "face/mouth.tsv"
    if tag in BODY_SWEAT:
        return "body/sweat.tsv"
    if "makeup" in tag:
        return "face/details.tsv"
    return "face/emotion.tsv"


def classify_sexual_emotion(tag: str) -> str:
    if tag in BODY_SWEAT:
        return "body/sweat.tsv"
    if tag in {"spit", "drool"}:
        return "body/fluids/saliva.tsv"
    if tag == "smile":
        return "face/mouth.tsv"
    if tag == "tongue":
        return "face/mouth.tsv"
    if tag in {"drunk", "cry"}:
        return "face/emotion.tsv"
    if tag in {";o", ":o"}:
        return "face/emoticons.tsv"
    if tag == "x-ray":
        return "style/techniques.tsv"
    if tag in {"stomach bulge", "abdominal bulge"}:
        return "body/abdomen.tsv"
    if tag == "crowd":
        return "scene/subject_matter.tsv"
    if tag in FACE_SEXUAL:
        return "face/sexual.tsv"
    if tag in FACE_EMOTION:
        return "face/emotion.tsv"
    if tag in FACE_EYES:
        return "face/eyes.tsv"
    if tag in FACE_MOUTH:
        return "face/mouth.tsv"
    if tag in {"motion lines"}:
        return "style/techniques.tsv"
    return "pose/action.tsv"


def classify_fullbody_attire(tag: str) -> str:
    if any(word in tag for word in ("leotard", "bodysuit", "bodystocking", "bikesuit", "bunnysuit", "jumpsuit", "plugsuit")):
        return "clothes/full/bodysuit.tsv"
    if "swimsuit" in tag:
        return "clothes/full/swimsuit.tsv"
    if "uniform" in tag:
        return "clothes/full/uniform.tsv"
    if "costume" in tag or tag in {"santa costume", "tuxedo", "suit", "tutu"}:
        return "clothes/full/costume.tsv"
    return "clothes/full/other.tsv"


def classify_accessory(tag: str) -> str:
    if any(word in tag for word in ("bag", "backpack", "pouch", "purse", "satchel", "briefcase", "holster", "quiver", "wallet")):
        return "clothes/accessory/bags.tsv"
    if any(word in tag for word in ("earring", "necklace", "bracelet", "ring", "jewelry", "jewel", "brooch", "pendant", "tiara", "crown")):
        return "clothes/accessory/jewelry.tsv"
    if any(word in tag for word in ("hat", "helmet", "cap", "bonnet", "veil", "mask", "goggles", "headphones", "sunglasses")):
        return "clothes/accessory/head.tsv"
    if any(word in tag for word in ("collar", "scarf", "necktie", "bowtie", "choker", "neck")):
        return "clothes/accessory/neck.tsv"
    if any(word in tag for word in ("arm", "ankle", "wrist", "glove", "garter")):
        return "clothes/accessory/limbs.tsv"
    return "clothes/accessory/misc.tsv"


def add_tag(
    pools: PoolMap,
    dest: str,
    raw_tag: str,
    count: int | None,
    related: str,
    source: str,
    danbooru_counts: dict[str, int],
    stats: Stats,
) -> None:
    tag = clean_tag(raw_tag)
    if not tag or not is_simple_tag(tag):
        stats.rows_skipped += 1
        return
    effective_count = count if count is not None else danbooru_counts.get(tag)
    row = pools[dest].get(tag)
    if row is None:
        row = TagRow(count=effective_count)
        pools[dest][tag] = row
        stats.rows_added += 1
    else:
        stats.duplicate_rows += 1
        if effective_count is not None and (row.count is None or effective_count > row.count):
            row.count = effective_count
    if related:
        for related_tag in related.split(","):
            cleaned = clean_tag(related_tag)
            if cleaned and is_simple_tag(cleaned):
                row.related.add(cleaned)
    if source:
        row.sources.add(source)


def write_pools(output: Path, pools: PoolMap, stats: Stats) -> None:
    for rel, rows in sorted(pools.items()):
        if not rows:
            continue
        path = output / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        sorted_tags = sorted(
            rows.items(),
            key=lambda item: (
                item[1].count is None,
                -(item[1].count or 0),
                item[0],
            ),
        )
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            writer.writerow(TSV_HEADER)
            for tag, row in sorted_tags:
                related = ", ".join(sorted(row.related))
                writer.writerow((tag, "" if row.count is None else str(row.count), related))
                stats.rows_written += 1
        stats.files_written += 1


def clean_tag(value: str) -> str:
    tag = TEMPLATE_RE.sub(" ", value)
    tag = tag.strip().strip(",|")
    match = WEIGHTED_RE.match(tag)
    if match:
        tag = match.group("tag")
    tag = tag.replace("_", " ")
    tag = " ".join(tag.split())
    return tag.lower()


def is_simple_tag(tag: str) -> bool:
    if not tag:
        return False
    if tag.startswith("(") and ":" in tag:
        return False
    return not any(token in tag for token in BAD_TOKENS)


def normalize_tag(value: str) -> str:
    return clean_tag(value)


def parse_count(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def count_tsv_rows(path: Path) -> int:
    return len(read_tsv(path))


if __name__ == "__main__":
    main()
