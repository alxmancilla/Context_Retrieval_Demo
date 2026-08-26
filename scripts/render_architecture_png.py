import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("public/solution-architecture.png")
W, H = 1600, 950
TEXT = "#09251d"
GREEN = "#116149"
BLUE = "#1f6feb"
ORANGE = "#b7791f"
RED = "#b42318"


def font(size: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


TITLE = font(36, True)
LABEL = font(23, True)
SMALL = font(18)
TINY = font(16)


def render() -> None:
    OUT.parent.mkdir(exist_ok=True)
    img = Image.new("RGB", (W, H), "#f7fbf8")
    draw = ImageDraw.Draw(img)

    def box(x, y, w, h, title, lines, fill, outline):
        draw.rounded_rectangle((x, y, x + w, y + h), radius=20, fill=fill, outline=outline, width=3)
        tw = draw.textlength(title, font=LABEL)
        draw.text((x + (w - tw) / 2, y + 18), title, fill=TEXT, font=LABEL)
        for i, line in enumerate(lines):
            lw = draw.textlength(line, font=SMALL)
            draw.text((x + (w - lw) / 2, y + 52 + i * 24), line, fill=TEXT, font=SMALL)

    def arrow(points, color=GREEN):
        draw.line(points, fill=color, width=4)
        x1, y1 = points[-2]
        x2, y2 = points[-1]
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 14
        left = (x2 - size * math.cos(angle - 0.45), y2 - size * math.sin(angle - 0.45))
        right = (x2 - size * math.cos(angle + 0.45), y2 - size * math.sin(angle + 0.45))
        draw.polygon([(x2, y2), left, right], fill=color)

    draw.text((52, 48), "Context Retrieval Demo - Designed/Implemented Architecture", fill=TEXT, font=TITLE)
    draw.rounded_rectangle((45, 105, 1555, 850), radius=26, fill="white", outline="#d5e7dc", width=3)

    box(85, 175, 210, 96, "Chainlit UI", ["answer + side tabs"], "#e8f5ee", GREEN)
    box(355, 175, 240, 96, "Identity Gate", ["realm, user, principals"], "#fdecec", RED)
    box(665, 175, 230, 96, "LangGraph", ["coordinator + state"], "#e8f5ee", GREEN)
    box(965, 175, 220, 96, "Intent", ["route + rewrite"], "#e8f5ee", GREEN)
    arrow([(295, 223), (355, 223)])
    arrow([(595, 223), (665, 223)])
    arrow([(895, 223), (965, 223)])

    box(675, 370, 285, 118, "Context Path", ["recent turns", "governed memory-v2", "non-authoritative"], "#e8f5ee", GREEN)
    box(1055, 370, 310, 118, "Source Agents", ["GitHub, Jira, SharePoint", "Confluence, Teams"], "#e8f5ee", GREEN)
    arrow([(1075, 271), (1075, 330), (820, 330), (820, 370)])
    arrow([(1075, 271), (1075, 330), (1210, 330), (1210, 370)])

    box(105, 392, 250, 90, "Checkpoints", ["execution state + TTL"], "#eef7ff", BLUE)
    box(405, 392, 250, 90, "Memory Nodes", ["typed, valid, versioned"], "#eef7ff", BLUE)
    arrow([(780, 271), (780, 320), (230, 320), (230, 392)])
    arrow([(675, 430), (655, 430)])

    box(1025, 585, 365, 118, "MongoDB Atlas", ["hybrid search: vector + lexical", "ACL filters before ranking", "governance + claims"], "#eef7ff", BLUE)
    arrow([(1210, 488), (1210, 585)])
    arrow([(1025, 645), (850, 645), (850, 488)])

    box(680, 645, 230, 90, "Voyage AI", ["global reranking"], "#fff7e6", ORANGE)
    box(385, 645, 240, 90, "Reconciliation", ["authority + freshness", "indexed claims"], "#e8f5ee", GREEN)
    box(105, 645, 210, 90, "Grove", ["grounded answer"], "#fff7e6", ORANGE)
    arrow([(1025, 645), (910, 690)])
    arrow([(680, 690), (625, 690)])
    arrow([(385, 690), (315, 690)])
    arrow([(105, 690), (70, 690), (70, 223), (85, 223)])

    box(1285, 760, 215, 60, "/ready checks", ["11 indexes + metrics"], "#eef7ff", BLUE)
    draw.text((70, 885), "Protected governance and indexed claim assertions determine truth. Model output is rebound only to retrieved citations.", fill=TEXT, font=TINY)
    img.save(OUT)


if __name__ == "__main__":
    render()
    print(OUT)
