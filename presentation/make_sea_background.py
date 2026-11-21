"""Render the game's sea + compass background at slide size (1920x1080)."""
import math, os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

W, H, S = 1920, 1080, 2.2          # S = compass scale vs. the in-game rose
pygame.init(); pygame.display.set_mode((1, 1))
surf = pygame.Surface((W, H))
for y in range(H):                   # same gradient as renderer._build_sea_base
    t = y / (H - 1)
    pygame.draw.line(surf, (int(10 + 9 * t), int(42 + 28 * t), int(66 + 26 * t)), (0, y), (W, y))

ov = pygame.Surface((W, H), pygame.SRCALPHA)
for x in range(0, W, 12):            # faint dot texture
    for y in range(0, H, 12):
        ov.set_at((x + (6 if (y // 12) % 2 else 0), y), (150, 205, 215, 42))
rx, ry = 190, H - 190                # compass rose, bottom-left
for a in range(0, 360, 30):
    r = math.radians(a)
    pygame.draw.line(ov, (130, 178, 188, 26), (rx, ry), (rx + math.cos(r) * 3000, ry + math.sin(r) * 3000), 2)
pygame.draw.circle(ov, (195, 170, 110, 70), (rx, ry), int(38 * S), 2)
pygame.draw.circle(ov, (195, 170, 110, 50), (rx, ry), int(26 * S), 2)
for a in (0, 90, 180, 270):
    r = math.radians(a)
    tip = (rx + math.cos(r) * 42 * S, ry + math.sin(r) * 42 * S)
    p1 = (rx + math.cos(r + .35) * 10 * S, ry + math.sin(r + .35) * 10 * S)
    p2 = (rx + math.cos(r - .35) * 10 * S, ry + math.sin(r - .35) * 10 * S)
    pygame.draw.polygon(ov, (220, 185, 105, 95), [(rx, ry), p1, tip])
    pygame.draw.polygon(ov, (140, 115, 65, 75), [(rx, ry), tip, p2])
for a in (45, 135, 225, 315):
    r = math.radians(a)
    tip = (rx + math.cos(r) * 26 * S, ry + math.sin(r) * 26 * S)
    p1 = (rx + math.cos(r + .35) * 7 * S, ry + math.sin(r + .35) * 7 * S)
    p2 = (rx + math.cos(r - .35) * 7 * S, ry + math.sin(r - .35) * 7 * S)
    pygame.draw.polygon(ov, (180, 155, 95, 65), [(rx, ry), p1, tip, p2])
pygame.draw.circle(ov, (236, 185, 94, 130), (rx, ry), 8)
surf.blit(ov, (0, 0))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "sea_background.png")
pygame.image.save(surf, out)
print("saved", out)
