"""Render the project's own dawn emblem as a multi-resolution Windows icon."""

from pathlib import Path

from PIL import Image, ImageDraw


def main():
    scale = 4
    image = Image.new("RGBA", (128 * scale, 128 * scale))
    draw = ImageDraw.Draw(image)
    green, gold = "#244b3c", "#d2bd7d"
    draw.rounded_rectangle((0, 0, 128 * scale - 1, 128 * scale - 1), 30 * scale, green)
    draw.arc(tuple(value * scale for value in (28, 46, 100, 118)), 180, 360, gold, 3 * scale)

    def line(points):
        points = [(round(x * scale), round(y * scale)) for x, y in points]
        draw.line(points, fill=gold, width=3 * scale, joint="curve")
        for x, y in (points[0], points[-1]):
            radius = 1.5 * scale
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=gold)

    for points in (
        [(22, 94), (106, 94)], [(33, 105), (95, 105)],
        [(64, 14), (64, 25)], [(23, 30), (31, 39)], [(105, 30), (97, 39)],
    ):
        line(points)
    for points in (
        [(48, 82), (49, 59), (77, 60), (82, 40)],
        [(58, 81), (59, 70), (76, 65), (81, 54)],
    ):
        curve = []
        for step in range(65):
            t = step / 64
            weights = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3]
            curve.append(tuple(sum(weight * point[axis] for weight, point in zip(weights, points)) for axis in (0, 1)))
        line(curve)
    destination = Path(__file__).resolve().parent / "assets/dawn-atelier.ico"
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="ICO", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    print(destination)


if __name__ == "__main__":
    main()
