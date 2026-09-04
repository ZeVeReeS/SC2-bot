import pyautogui
import time
import os

# Папка, где лежит сам скрипт — картинку ищем рядом с ним
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BARREL_IMG = os.path.join(SCRIPT_DIR, 'barrel_icon.png')

CONFIDENCE_LEVEL = 0.8

# Убираем стандартную паузу pyautogui после КАЖДОГО действия (по умолчанию 0.1 сек) —
# это и есть основной источник задержки, которую можно убрать.
pyautogui.PAUSE = 0


def get_unique_targets(image_path, tolerance=20):
    """Находит все совпадения на экране и удаляет дубликаты координат-соседей"""
    try:
        matches = list(pyautogui.locateAllOnScreen(image_path, confidence=CONFIDENCE_LEVEL))
    except Exception:
        matches = []

    unique_points = []
    for m in matches:
        center = pyautogui.center(m)
        if not any(abs(center.x - u[0]) < tolerance and abs(center.y - u[1]) < tolerance for u in unique_points):
            unique_points.append((center.x, center.y))
    return unique_points


def main():
    print("У тебя 3 секунды, чтобы переключиться в игру...")
    time.sleep(3)

    targets = get_unique_targets(BARREL_IMG)

    if len(targets) < 2:
        print(f"Найдено только {len(targets)} подходящих иконок на экране, нужно минимум 2.")
        return

    # Сортируем в порядке чтения: сверху вниз, затем слева направо —
    # чтобы "первые два" были действительно первыми по расположению на экране.
    targets.sort(key=lambda p: (p[1], p[0]))
    first_two = targets[:2]

    for i, (x, y) in enumerate(first_two):
        print(f"Клик x2 по иконке #{i + 1} ({x}, {y})")
        # clicks=2, interval=0 -> два клика подряд без паузы между ними
        pyautogui.click(x, y, clicks=2, interval=0)


if __name__ == "__main__":
    main()
