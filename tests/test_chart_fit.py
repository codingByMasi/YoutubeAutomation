"""Chart titles and big numbers stay inside the 1920x1080 frame (a long title used to run off the right edge)."""
from studio.providers import charts


def _inside(fig, text) -> bool:
    fig.canvas.draw()
    box = text.get_window_extent(fig.canvas.get_renderer())
    return box.x0 >= 0 and box.x1 <= charts.W


def test_long_title_wraps_inside_frame():
    fig = charts._fig()
    charts._frame(fig, "1833 Abolition Act: £20 million in loans, about 40% of that year's government spending", "")
    title = fig.texts[0]
    assert title.get_text().count("\n") == 1
    assert _inside(fig, title)


def test_big_number_fits_frame():
    text = charts.fmt(20, "million pounds")
    fig = charts._fig()
    t = fig.text(0.5, 0.5, text, ha="center", fontsize=charts.fit_size(text, 180, min_size=60), fontweight="bold")
    assert _inside(fig, t)
    assert charts.fit_size("5", 180, min_size=60) == 180
