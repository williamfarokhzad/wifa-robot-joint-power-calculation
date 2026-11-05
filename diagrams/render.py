"""Regenerate editable figures from the two supplied synthetic CSV traces."""
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from joint_power import read_samples

W, H = 800, 460
L, R, T, B = 104, 746, 124, 366


def draw(stem, title, subtitle, ymin, ymax, ticks_y, ticks_t, breaks, note):
    left, right = read_samples(HERE.parent / "examples" / f"{stem}.csv")
    dt = right.time_s - left.time_s
    a, b = left.torque_nm, right.torque_nm
    c, d = left.speed_rpm, right.speed_rpm

    def p(t):
        u = t / dt
        return (a + (b-a)*u) * (c + (d-c)*u) * math.pi/30

    def x(t):
        return L + (R-L) * t/dt

    def y(w):
        return B - (B-T) * (w-ymin)/(ymax-ymin)

    def label(x, y, s, size=22, extra=""):
        return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" {extra}>{s}</text>'

    def line(x1, y1, x2, y2, stroke, width=1, more=""):
        return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{width}" {more}/>'

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
           f"<title>{title}</title><desc>{note}</desc>",
           '<rect width="800" height="460" rx="24" fill="#edf5f6"/>',
           '<g font-family="DejaVu Sans, sans-serif" fill="#183948">',
           label(32, 49, title, 29, 'font-weight="bold"'),
           label(32, 83, subtitle, 20),
           f'<rect x="{L}" y="{T}" width="{R-L}" height="{B-T}" fill="#fff" rx="6"/>']
    for w in ticks_y:
        svg.extend([line(L, y(w), R, y(w), "#cadadd"),
                    label(L-14, y(w)+7, str(w), 19, 'text-anchor="end"')])
    for t in ticks_t:
        svg.extend([line(x(t), T, x(t), B, "#e1ecee"),
                    label(x(t), B+29, str(t), 19, 'text-anchor="middle"')])
    svg.append(line(L, y(0), R, y(0), "#48616b", 2))
    svg += [label(L, T-10, "Joint power (W)", 18), label(R, B+56, "Time (s)", 20, 'text-anchor="end"')]
    for lo, hi in zip(breaks, breaks[1:]):
        mid = (lo+hi)/2
        # The three sampled points specify the exact quadratic Bézier curve.
        cy = 2*y(p(mid)) - (y(p(lo))+y(p(hi)))/2
        curve = f'M {x(lo):.2f} {y(p(lo)):.2f} Q {x(mid):.2f} {cy:.2f} {x(hi):.2f} {y(p(hi)):.2f}'
        pos = p(mid) >= 0
        fill, stroke = ("#a8e2d7", "#087368") if pos else ("#ffcbae", "#a43d16")
        svg.append(f'<path d="{curve} L {x(hi):.2f} {y(0):.2f} L {x(lo):.2f} {y(0):.2f} Z" fill="{fill}"/>')
        svg.append(f'<path d="{curve}" fill="none" stroke="{stroke}" stroke-width="4"/>')
    for t in (0, dt):
        svg.append(f'<circle cx="{x(t):.2f}" cy="{y(p(t)):.2f}" r="6" fill="#163949"/>')
    if stem == "coupled-ramp":
        svg.append(line(x(1), y(0), x(1), y(p(1)), "#0a6059", 2, 'stroke-dasharray="5 5"'))
        svg.append(label(x(1)+12, y(p(1))-5, "9.425 W peak", 21, 'font-weight="bold"'))
    else:
        for t in breaks[1:-1]:
            svg.append(f'<circle cx="{x(t):.2f}" cy="{y(0):.2f}" r="5" fill="#183948"/>')
        svg.append(label(x(2), y(p(2))+27, "Braking", 21, 'text-anchor="middle" font-weight="bold" fill="#893713"'))
    svg += [label(32, 438, note, 17), "</g></svg>"]
    out = HERE / f"joint-power-{stem}.svg"
    out.write_text("\n".join(svg)+"\n", encoding="utf-8")
    return out


def main():
    figures = [
        draw("coupled-ramp", "Zero at both samples, positive in between",
             "A falling speed and rising torque multiply into a curve.",
             0, 12, [0, 3, 6, 9, 12], [0, 0.5, 1, 1.5, 2], [0, 2],
             "Dark dots are input times. The curve is an interpolation, not a recording."),
        draw("two-crossings", "Positive endpoints can hide braking",
             "Speed crosses zero at 1 s. Torque crosses zero at 3 s.",
             -10, 22, [-10, -5, 0, 5, 10, 15, 20], [0, 1, 2, 3, 4], [0, 1, 3, 4],
             "Green area is motoring work. Orange area is work absorbed at the joint."),
    ]
    for svg in figures:
        # Inkscape renders the editable SVG; ImageMagick encodes WebP.
        png = svg.with_suffix(".png")
        try:
            subprocess.run(["inkscape", str(svg), f"--export-filename={png}"], check=True)
            subprocess.run(["convert", str(png), "-strip", "-quality", "86",
                            str(svg.with_suffix(".webp"))], check=True)
        finally:
            png.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
