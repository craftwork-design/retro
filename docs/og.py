from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
img = Image.new("RGB", (W, H), "#000000")
d = ImageDraw.Draw(img)

FONT = "/System/Library/Fonts/Menlo.ttc"

wordmark = ["█▀█ █▀▀ ▀█▀ █▀█ █▀█",
            "█▀▄ █▀▀  █  █▀▄ █ █",
            "▀ ▀ ▀▀▀  ▀  ▀ ▀ ▀▀▀"]
band = "░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓"

wf = ImageFont.truetype(FONT, 62, index=0)
# measure the FULL block cell (top of █ to bottom) so rows tile with no gap
a0, b0, a1, b1 = d.textbbox((0, 0), "█", font=wf)
ch = b1 - b0
line_adv = int(round(ch * 0.995))      # tile vertical blocks seamlessly
top_off = b0                           # ink starts below the pen y by this

wm_w = int(d.textlength(wordmark[0], font=wf))
x0 = (W - wm_w) // 2
y0 = 150

for i, ln in enumerate(wordmark):
    d.text((x0, y0 + i * line_adv), ln, font=wf, fill="#ffffff")

# shimmer band under the wordmark
by = y0 + 3 * line_adv + 6
d.text((x0, by), band, font=wf, fill="#5a5a5a")

# tagline
tf = ImageFont.truetype(FONT, 34, index=0)
tag = "never type the same correction twice."
tw = int(d.textlength(tag, font=tf))
d.text(((W - tw) // 2, by + line_adv + 40), tag, font=tf, fill="#ffffff")

# url
uf = ImageFont.truetype(FONT, 26, index=0)
url = "retro.craftwork.design"
uw = int(d.textlength(url, font=uf))
d.text(((W - uw) // 2, H - 78), url, font=uf, fill="#8a8a8a")

out = "og.png"
img.save(out)
print("saved", out, img.size)
