from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 900
BG = "#fffdf8"
INK = "#1f2933"
MUTED = "#596579"
BLUE = "#2563eb"
RED = "#dc2626"
GREEN = "#15803d"
ORANGE = "#ea580c"
PURPLE = "#7c3aed"


FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


TITLE = load_font(42)
HEAD = load_font(30)
BODY = load_font(24)
SMALL = load_font(20)


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, width: int) -> int:
    x, y = xy
    for paragraph in text.split("\n"):
        lines = textwrap.wrap(paragraph, width=width, break_long_words=False) or [""]
        for line in lines:
            draw.text((x, y), line, fill=INK, font=font)
            y += 34
        y += 6
    return y


def axis(draw: ImageDraw.ImageDraw, origin: tuple[int, int], x_end: tuple[int, int], y_end: tuple[int, int]) -> None:
    draw.line([origin, x_end], fill=INK, width=4)
    draw.line([origin, y_end], fill=INK, width=4)
    draw.polygon([(x_end[0], x_end[1]), (x_end[0] - 16, x_end[1] - 8), (x_end[0] - 16, x_end[1] + 8)], fill=INK)
    draw.polygon([(y_end[0], y_end[1]), (y_end[0] - 8, y_end[1] + 16), (y_end[0] + 8, y_end[1] + 16)], fill=INK)


def base(title: str, stem: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 112), fill="#f4f7fb")
    draw.text((50, 32), title, fill=INK, font=TITLE)
    draw_wrapped(draw, (50, 130), stem, BODY, 56)
    return image, draw


def tax_wedge(path: Path) -> None:
    image, draw = base(
        "经济学考研题 1：税收楔子与无谓损失",
        "已知某商品市场需求曲线 D、供给曲线 S。政府对每单位商品征收从量税 t。请说明买方支付价格 Pb、卖方得到价格 Ps、交易量变化，以及税收收入和无谓损失。",
    )
    ox, oy = 210, 760
    axis(draw, (ox, oy), (1080, oy), (ox, 260))
    draw.text((1088, oy - 8), "Q 数量", fill=INK, font=SMALL)
    draw.text((178, 228), "P 价格", fill=INK, font=SMALL)
    draw.line([(250, 700), (1010, 320)], fill=BLUE, width=5)
    draw.text((1015, 300), "S", fill=BLUE, font=HEAD)
    draw.line([(250, 280), (1010, 700)], fill=RED, width=5)
    draw.text((1015, 690), "D", fill=RED, font=HEAD)
    draw.line([(250, 610), (1010, 230)], fill=GREEN, width=5)
    draw.text((1015, 218), "S+t", fill=GREEN, font=HEAD)
    draw.rectangle((560, 420, 720, 575), outline=ORANGE, width=4)
    draw.polygon([(720, 420), (835, 480), (720, 575)], outline=PURPLE, fill=None)
    draw.text((540, 382), "税收收入", fill=ORANGE, font=SMALL)
    draw.text((842, 476), "DWL", fill=PURPLE, font=SMALL)
    draw.line([(560, oy), (560, 575)], fill=MUTED, width=3)
    draw.line([(835, oy), (835, 480)], fill=MUTED, width=3)
    draw.text((538, oy + 12), "Q1", fill=INK, font=SMALL)
    draw.text((812, oy + 12), "Q0", fill=INK, font=SMALL)
    draw.text((478, 408), "Pb", fill=INK, font=SMALL)
    draw.text((478, 562), "Ps", fill=INK, font=SMALL)
    image.save(path)


def consumer_choice(path: Path) -> None:
    image, draw = base(
        "经济学考研题 2：消费者选择与价格效应",
        "消费者购买 X 与 Y 两种商品。X 价格下降后，预算线绕纵轴向外旋转。请用替代效应和收入效应解释最优消费点从 A 到 C 的变化，并标出补偿预算线与点 B。",
    )
    ox, oy = 250, 760
    axis(draw, (ox, oy), (1090, oy), (ox, 250))
    draw.text((1085, oy + 16), "X", fill=INK, font=HEAD)
    draw.text((220, 230), "Y", fill=INK, font=HEAD)
    draw.line([(ox, 310), (760, oy)], fill=MUTED, width=4)
    draw.line([(ox, 310), (1030, oy)], fill=BLUE, width=5)
    draw.line([(ox, 425), (920, oy)], fill=ORANGE, width=4)
    draw.arc((355, 505, 770, 925), start=205, end=330, fill=RED, width=5)
    draw.arc((500, 420, 1000, 940), start=205, end=330, fill=GREEN, width=5)
    for label, point, color in (
        ("A", (565, 585), RED),
        ("B", (690, 635), ORANGE),
        ("C", (825, 610), GREEN),
    ):
        draw.ellipse((point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8), fill=color)
        draw.text((point[0] + 14, point[1] - 26), label, fill=color, font=HEAD)
    draw.text((760, 792), "原预算线", fill=MUTED, font=SMALL)
    draw.text((930, 725), "新预算线", fill=BLUE, font=SMALL)
    draw.text((650, 680), "补偿预算线", fill=ORANGE, font=SMALL)
    draw.text((670, 506), "替代效应", fill=PURPLE, font=SMALL)
    draw.text((805, 554), "收入效应", fill=PURPLE, font=SMALL)
    image.save(path)


def monopoly(path: Path) -> None:
    image, draw = base(
        "经济学考研题 3：垄断定价与福利损失",
        "垄断厂商面对向右下方倾斜的需求曲线 D，边际收益曲线 MR 位于其下方。已知 MC 为水平线。请找出 MR=MC 的产量 Qm、垄断价格 Pm，并比较完全竞争产量 Qc。",
    )
    ox, oy = 230, 760
    axis(draw, (ox, oy), (1080, oy), (ox, 250))
    draw.line([(285, 315), (1010, 710)], fill=BLUE, width=5)
    draw.text((1018, 700), "D", fill=BLUE, font=HEAD)
    draw.line([(285, 430), (870, 730)], fill=RED, width=5)
    draw.text((880, 718), "MR", fill=RED, font=HEAD)
    draw.line([(285, 565), (1030, 565)], fill=GREEN, width=5)
    draw.text((1040, 548), "MC", fill=GREEN, font=HEAD)
    draw.line([(590, oy), (590, 565)], fill=MUTED, width=3)
    draw.line([(845, oy), (845, 565)], fill=MUTED, width=3)
    draw.line([(ox, 395), (590, 395)], fill=MUTED, width=3)
    draw.rectangle((590, 395, 845, 565), outline=ORANGE, width=4)
    draw.polygon([(590, 395), (845, 565), (590, 565)], outline=PURPLE, fill=None)
    draw.text((565, oy + 12), "Qm", fill=INK, font=SMALL)
    draw.text((820, oy + 12), "Qc", fill=INK, font=SMALL)
    draw.text((174, 382), "Pm", fill=INK, font=SMALL)
    draw.text((690, 365), "垄断利润", fill=ORANGE, font=SMALL)
    draw.text((710, 586), "DWL", fill=PURPLE, font=SMALL)
    image.save(path)


def externality(path: Path) -> None:
    image, draw = base(
        "经济学考研题 4：负外部性与庇古税",
        "某生产活动存在负外部性，私人边际成本 MPC 低于社会边际成本 MSC。请解释市场均衡数量 Qm 为什么大于社会最优数量 Q*，并说明庇古税如何使 MPC 上移。",
    )
    ox, oy = 230, 760
    axis(draw, (ox, oy), (1080, oy), (ox, 250))
    draw.line([(270, 705), (1000, 330)], fill=GREEN, width=5)
    draw.text((1008, 314), "MPC", fill=GREEN, font=HEAD)
    draw.line([(270, 620), (1000, 245)], fill=ORANGE, width=5)
    draw.text((1008, 230), "MSC", fill=ORANGE, font=HEAD)
    draw.line([(270, 320), (1000, 705)], fill=BLUE, width=5)
    draw.text((1008, 696), "MSB=D", fill=BLUE, font=HEAD)
    draw.line([(565, oy), (565, 475)], fill=MUTED, width=3)
    draw.line([(755, oy), (755, 575)], fill=MUTED, width=3)
    draw.polygon([(565, 475), (755, 575), (565, 575)], outline=PURPLE, fill=None)
    draw.text((535, oy + 12), "Q*", fill=INK, font=SMALL)
    draw.text((728, oy + 12), "Qm", fill=INK, font=SMALL)
    draw.text((606, 540), "过度生产损失", fill=PURPLE, font=SMALL)
    draw.text((390, 390), "庇古税 = MSC - MPC", fill=ORANGE, font=SMALL)
    image.save(path)


def is_lm(path: Path) -> None:
    image, draw = base(
        "经济学考研题 5：IS-LM 与财政扩张",
        "在 IS-LM 模型中，政府购买增加。请说明 IS 曲线右移后利率 r 和产出 Y 的变化，并解释挤出效应为什么使产出增量小于简单乘数。",
    )
    ox, oy = 245, 760
    axis(draw, (ox, oy), (1080, oy), (ox, 250))
    draw.line([(310, 350), (950, 710)], fill=BLUE, width=5)
    draw.text((955, 698), "IS0", fill=BLUE, font=HEAD)
    draw.line([(430, 315), (1070, 675)], fill=RED, width=5)
    draw.text((1074, 656), "IS1", fill=RED, font=HEAD)
    draw.line([(480, 720), (835, 310)], fill=GREEN, width=5)
    draw.text((840, 292), "LM", fill=GREEN, font=HEAD)
    draw.ellipse((620, 526, 638, 544), fill=BLUE)
    draw.ellipse((730, 426, 748, 444), fill=RED)
    draw.line([(629, oy), (629, 535)], fill=MUTED, width=3)
    draw.line([(739, oy), (739, 435)], fill=MUTED, width=3)
    draw.line([(ox, 535), (629, 535)], fill=MUTED, width=3)
    draw.line([(ox, 435), (739, 435)], fill=MUTED, width=3)
    draw.text((606, oy + 12), "Y0", fill=INK, font=SMALL)
    draw.text((716, oy + 12), "Y1", fill=INK, font=SMALL)
    draw.text((190, 522), "r0", fill=INK, font=SMALL)
    draw.text((190, 422), "r1", fill=INK, font=SMALL)
    draw.text((745, 494), "利率上升", fill=PURPLE, font=SMALL)
    draw.text((785, 735), "产出增加但存在挤出效应", fill=PURPLE, font=SMALL)
    image.save(path)


CASES = (
    ("01-tax-wedge.png", tax_wedge),
    ("02-consumer-choice.png", consumer_choice),
    ("03-monopoly.png", monopoly),
    ("04-externality.png", externality),
    ("05-is-lm.png", is_lm),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Chinese economics image fixtures for Aegis vision acceptance.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/aegis-vision-economics-fixtures"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, draw_case in CASES:
        path = args.output_dir / filename
        draw_case(path)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
