"""Restore the deck's CSS animations in the exported HTML presentation.

The Slides "Web page" export keeps every element but drops custom @keyframes
animations. This script injects them back, matching elements by their image
description or exported style.

Usage (from the project root):
    py presentation/patch_export.py "Game of Thrones AI Conquest Presentation.html"
Safe to run more than once.
"""
import sys

MARK = "/* got-animations-patch */"
CSS = MARK + """
@keyframes gotHover{from{transform:translateY(0)}to{transform:translateY(-16px)}}
@keyframes gotCourier{from{transform:translateX(0);opacity:0}10%{opacity:1}50%{transform:translateX(560px) translateY(-40px)}90%{opacity:1}to{transform:translateX(1180px);opacity:0}}
@keyframes gotToken{from{transform:translateX(130px);opacity:0}8%{opacity:1}92%{opacity:1}to{transform:translateX(1630px);opacity:0}}
@keyframes gotMarch{from{transform:translateX(0)}to{transform:translateX(1500px)}}
@keyframes gotGlow{from{filter:drop-shadow(0 0 0 rgba(224,180,94,0))}to{filter:drop-shadow(0 0 20px rgba(224,180,94,.75))}}
/* corner dragons on content slides */
div[data-frame-id][style*="left: 1700px"] img{animation:gotHover 3s ease-in-out infinite alternate}
/* large gold dragon on cover and closing */
img[alt^="Lannister golden dragon"]{animation:gotHover 3s ease-in-out infinite alternate}
/* raven carrying the alliance offer */
img[alt="Raven carrying the offer"]{animation:gotCourier 4.5s ease-in-out infinite}
/* glowing tokens travelling through the complete-flow lanes */
div[style*="background-color: rgb(255, 231, 168)"]{animation:gotToken 5s linear infinite}
/* marching warriors on the closing slide */
img[alt="Warrior marching"]{animation:gotMarch 12s linear infinite}
/* glowing crossed swords on the battle slide */
img[alt="Crossed swords"]{animation:gotGlow 2.4s ease-in-out infinite alternate}
@media (prefers-reduced-motion: reduce){img,div{animation:none!important}}
"""

path = sys.argv[1] if len(sys.argv) > 1 else "Game of Thrones AI Conquest Presentation.html"
html = open(path, encoding="utf-8").read()
if MARK in html:
    print("already patched")
    sys.exit(0)
i = html.find("</head>")
if i < 0:
    sys.exit("no </head> found")
html = html[:i] + "<style>" + CSS + "</style>" + html[i:]
open(path, "w", encoding="utf-8", newline="").write(html)
print("patched:", path)
